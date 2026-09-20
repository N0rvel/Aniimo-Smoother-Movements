"""Refresh steering state on permitted input, after all original movement gates."""
import hashlib
import struct
from luajit_base import Reader, prototypes, need
from luajit_patch import abc, ad, uleb, MARKER

ENTRY = 'xfs/luascripts/GameApp/Controller/PawnController.lua'
ORIGINAL_SHA = '106f59a5936efc20a61d9a672e6f38666d6c09780c7cd29cf2994c7325dfd749'
PATCHED_SHA = 'a200db8a5b9a81a26a3a8ba834a9c1a91da46bbf86615d63d148dc86618c5339'


def edit(raw, proto):
    r=Reader(raw)
    flags,params,frame,nuv=r.take(4)
    ngc,nnum,nbc=r.uleb(),r.uleb(),r.uleb()
    nd=r.uleb()
    if nd:r.uleb();r.uleb()
    code=list(struct.unpack('<'+'I'*nbc,r.take(nbc*4)))
    uv=r.take(nuv*2)
    constants=raw[r.pos:len(raw)-nd if nd else len(raw)]
    need(params==4 and nbc==158 and nnum==1 and nuv==3, 'Unexpected movement-input routine.')
    keys=list(proto.constants);extra=[]
    def key(name):
        if name not in keys:
            keys.append(name);b=name.encode();extra.insert(0,uleb(len(b)+5)+b)
        return keys.index(name)
    model,method,component,guard,marker=map(key,('eModel','SetSteeringDeceleration','COMPONENT_MOTION','hasEModelComponent',MARKER))
    need(len(keys)<256,'Too many constants.')
    # R1/R2/R3 are the original axes AFTER all original movement gates;
    # R4 is the exact pawn receiving OnHandleMove; U2 is Common.Const.Const.
    call=[abc(54,7,4,model),ad(18,9,7),abc(54,7,7,method),ad(48,10,2),
          abc(54,10,10,component),ad(43,11,1),ad(41,12,1),abc(66,7,1,5),
          ad(43,7,2),abc(63,7,4,marker)]
    has_component=[ad(18,9,4),abc(54,7,4,guard),ad(48,10,2),abc(54,10,10,component),
                   abc(66,7,2,3),ad(15,0,7),ad(88,8,32768+len(call))]
    # Exactly the game's existing x~=0 or y~=0 test shape, including numeric
    # constant 0. No axis normalization, time-based retry or input substitution.
    block=[ad(7,1,0),ad(88,7,32768+2),ad(6,2,0),
           ad(88,7,32768+len(has_component)+len(call))]+has_component+call
    need(code[148]==abc(54,7,4,model) and code[-1]==ad(75,0,1),'Input dispatch changed.')
    for i,word in enumerate(code[:148]):
        if word&255==88:
            need(i+1+(word>>16)-32768<=148,'Branch crosses insertion point.')
    code[148:148]=block
    return (bytes((flags,params,max(frame,14),nuv))+uleb(len(keys))+uleb(nnum)+uleb(len(code))+b'\0'+
            struct.pack('<'+'I'*len(code),*code)+uv+b''.join(extra)+constants)


def patch(data):
    h=hashlib.sha256(data).hexdigest()
    if h==PATCHED_SHA:return data,{'state':'equal','hook':'permitted movement input'}
    need(h==ORIGINAL_SHA,'Unsupported PawnController script; no files were changed.')
    ps=prototypes(data);need(len(ps)==17,'Unexpected pawn prototype count.')
    r=Reader(data);need(r.take(4)==b'\x1bLJ\x02' and r.uleb()==8,'Unsupported Lua format.')
    r.take(r.uleb());out=bytearray(data[:r.pos]);ordinal=0
    while True:
        start=r.pos;size=r.uleb()
        if not size:out+=b'\0';break
        raw=r.take(size)
        if ordinal==3:
            new=edit(raw,ps[ordinal]);out+=uleb(len(new))+new
        else:out+=data[start:r.pos]
        ordinal+=1
    need(r.pos==len(data),'Trailing data.')
    result=bytes(out);newps=prototypes(result)
    need(len(ps)==len(newps),'Prototype count changed.')
    for i,(before,after) in enumerate(zip(ps,newps)):
        if i!=3:need(before.code==after.code and before.constants==after.constants,'Unrelated pawn routine changed.')
    need(hashlib.sha256(result).hexdigest()==PATCHED_SHA,'Patched pawn hash mismatch.')
    return result,{'state':'original','hook':'permitted movement input'}
