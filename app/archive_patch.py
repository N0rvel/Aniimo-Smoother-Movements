"""Replace one stored Lua ZIP entry and update its resource index.

All other entry payloads are kept byte for byte, including a camera fix.
"""
import hashlib
import io
import json
import struct
import zipfile
import zlib
from luajit_patch import need, patch
import pawn_patch

ENTRY = 'xfs/luascripts/Entities/SpaceEntities/CommonComponent/ClientMotionComponent.lua'


def sha(data):
    return hashlib.sha256(data).hexdigest()


def md5(data):
    return hashlib.md5(data).hexdigest()


def read_json(data):
    def unique(pairs):
        d = {}
        for k,v in pairs:
            need(k not in d, 'Duplicate JSON key.')
            d[k] = v
        return d
    return json.loads(data, object_pairs_hook=unique)


def replace_entry(archive, index, new_script, entry=ENTRY):
    need(len(archive) < 2**32, 'ZIP64 is unsupported.')
    meta = read_json(index)
    need(meta.get('CMSign') == 0 and meta.get('CMDataLen') == len(archive)
         and meta.get('CMDataMD5') == md5(archive), 'Archive/index mismatch.')
    with zipfile.ZipFile(io.BytesIO(archive)) as z:
        infos = z.infolist()
        need(len({i.filename for i in infos}) == len(infos), 'Duplicate archive entry.')
        need(z.testzip() is None, 'Corrupt resource archive.')
        matches = [i for i in infos if i.filename == entry]
        need(len(matches) == 1, 'Movement script missing or duplicated.')
        info = matches[0]
        need(info.compress_type == zipfile.ZIP_STORED and not info.flag_bits & 9,
             'Compressed/encrypted/streamed movement scripts are unsupported.')
        old_script = z.read(info)
    rows = meta.get('CMList')
    need(isinstance(rows,list) and len(rows) == meta.get('CMEntryNum') == len(infos),
         'Invalid resource index count.')
    need(len({e.get('CEName') for e in rows}) == len(rows), 'Duplicate resource index entry.')
    by_name = {e['CEName']:e for e in rows}
    for ordinal, item in enumerate(infos):
        row = by_name.get(item.filename,{})
        h = item.header_offset
        need(archive[h:h+4] == b'PK\x03\x04', 'Invalid local ZIP header.')
        nl,el = struct.unpack_from('<HH',archive,h+26)
        need(row.get('CEIndex') == ordinal and row.get('CEContainer') == 0
             and row.get('CEOffset') == h+30+nl+el
             and row.get('CESize') == item.file_size and row.get('CECSize') == item.compress_size,
             'Resource index does not match archive offsets/sizes.')
    row = by_name[entry]
    need(row['CEMD5'] == md5(old_script), 'Movement script checksum mismatch.')
    local, start = info.header_offset, row['CEOffset']
    end_data = start + len(old_script)
    need(archive[start:end_data] == old_script, 'Movement payload offset mismatch.')
    end = -1
    for p in range(len(archive)-22,max(-1,len(archive)-65558),-1):
        if archive[p:p+4] == b'PK\x05\x06' and p+22+struct.unpack_from('<H',archive,p+20)[0] == len(archive):
            end = p
            break
    need(end >= 0, 'ZIP end directory missing.')
    disk,cdisk,dcount,count,csize,central = struct.unpack_from('<HHHHII',archive,end+4)
    need(disk == cdisk == 0 and dcount == count == len(infos) and central+csize == end
         and end_data <= central, 'Split/ZIP64/unusual archives are unsupported.')
    delta = len(new_script)-len(old_script)
    result = bytearray(archive[:start]+new_script+archive[end_data:])
    crc = zlib.crc32(new_script) & 0xffffffff
    struct.pack_into('<III',result,local+14,crc,len(new_script),len(new_script))
    pos = central+delta
    found = 0
    for _ in range(count):
        need(result[pos:pos+4] == b'PK\x01\x02', 'Invalid central directory.')
        nl,el,cl = struct.unpack_from('<HHH',result,pos+28)
        name = bytes(result[pos+46:pos+46+nl])
        offset = struct.unpack_from('<I',result,pos+42)[0]
        if name == entry.encode():
            need(offset == local, 'Movement header mismatch.')
            struct.pack_into('<III',result,pos+16,crc,len(new_script),len(new_script))
            found += 1
        elif offset >= end_data:
            struct.pack_into('<I',result,pos+42,offset+delta)
        pos += 46+nl+el+cl
    need(found == 1 and pos == end+delta, 'Invalid directory layout.')
    struct.pack_into('<I',result,end+delta+16,central+delta)
    for item in rows:
        if item['CEOffset'] >= end_data:
            item['CEOffset'] += delta
    row['CESize'] = row['CECSize'] = len(new_script)
    row['CEMD5'] = md5(new_script)
    meta['CMDataLen'],meta['CMDataMD5'] = len(result),md5(result)
    new_index = json.dumps(meta,separators=(',',':'),ensure_ascii=False).encode('utf-8')
    with zipfile.ZipFile(io.BytesIO(result)) as z:
        need(z.testzip() is None and z.read(entry) == new_script, 'Patched ZIP verification failed.')
        for item in z.infolist():
            h = item.header_offset
            nl,el = struct.unpack_from('<HH',result,h+26)
            need(by_name[item.filename]['CEOffset'] == h+30+nl+el, 'Patched index offset mismatch.')
    return bytes(result),new_index


def transform_motion(archive,index):
    meta = read_json(index)
    need(meta.get('CMVersion') == 3551601, 'This release supports resource build 3551601 only.')
    with zipfile.ZipFile(io.BytesIO(archive)) as z:
        old = z.read(ENTRY)
    need(len(old) < 16*1024*1024, 'Oversized movement script.')
    new,detail = patch(old)
    detail.update({'build':meta.get('CMVersion'),'entry':ENTRY,'script_before':sha(old),'script_after':sha(new)})
    need(meta.get('CMDataMD5') == md5(archive) and meta.get('CMDataLen') == len(archive),
         'Archive/index mismatch.')
    if detail['state'] == 'equal':
        with zipfile.ZipFile(io.BytesIO(archive)) as z:
            need(z.testzip() is None, 'Corrupt installed archive.')
        return archive,index,detail
    new_archive,new_index = replace_entry(archive,index,new)
    return new_archive,new_index,detail


def transform(archive,index):
    # Preflight both scripts before constructing any replacement resource.
    with zipfile.ZipFile(io.BytesIO(archive)) as z:
        old_pawn=z.read(pawn_patch.ENTRY)
        need(len(old_pawn)<16*1024*1024, 'Oversized pawn script.')
        new_pawn,pawn_detail=pawn_patch.patch(old_pawn)
    result,new_index,motion_detail=transform_motion(archive,index)
    if old_pawn!=new_pawn:
        result,new_index=replace_entry(result,new_index,new_pawn,pawn_patch.ENTRY)
    detail=dict(motion_detail)
    detail['state']='equal' if motion_detail['state']=='equal' and pawn_detail['state']=='equal' else 'original'
    detail['hook']='control lifecycle + permitted movement input'
    detail['pawn_entry']=pawn_patch.ENTRY
    detail['pawn_before']=sha(old_pawn)
    detail['pawn_after']=sha(new_pawn)
    return result,new_index,detail
