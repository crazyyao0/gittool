import os, glob, zlib, re
from datetime import datetime
from datetime import timezone
from io import StringIO, BytesIO
from enum import IntEnum
from struct import unpack
from functools import lru_cache

class GitObjectType(IntEnum):
    commit = 1
    tree = 2
    blob = 3
    tag = 4
    ofs_delta = 6
    ref_delta = 7


class DiffObject:

    def __init__(self, commitid, filepath, method, fileid1, fileid2):
        self.commitid = commitid
        self.filepath = filepath
        self.method = method
        self.fileid1 = fileid1
        self.fileid2 = fileid2


class GitCommitObject:
    type = GitObjectType.commit
    def __init__(self, objid, raw):
        self.objid = objid
        self.seq = 0
        self.raw = raw
        self.tree = None
        self.parent = None
        self.mergefrom = None
        self.author = None
        self.committer = None
        self.createtime = None
        self.committime = None
        self.gpgsig = None
        self.msg = None
        buf = StringIO(raw.decode())
        while True:
            line = buf.readline().strip("\n")
            if line == "":
                break
            elif line.startswith("tree "):
                self.tree = bytes.fromhex(line[5:])
            elif line.startswith("parent "):
                if self.parent:
                    self.mergefrom = bytes.fromhex(line[7:])
                else:
                    self.parent = bytes.fromhex(line[7:])
            elif line.startswith("author "):
                p = re.match("([^<]+) <[^>]+> (\\d+) [0-9+-]+", line[7:])
                if p:
                    self.author = p[1]
                    self.createtime = int(p[2])
            elif line.startswith("committer "):
                p = re.match("(\\w+) <[^>]+> (\\d+) [0-9+-]+", line[10:])
                if p:
                    self.committer = p[1]
                    self.committime = int(p[2])
            elif line.startswith("gpgsig"):
                lines = [line[6:]]
                while True:
                    line=buf.readline()
                    lines.append(line)
                    if "END PGP SIGNATURE" in line:
                        self.gpgsig = "\n".join(lines)
                        break
        self.msg = buf.read()

    def __str__(self):
        ret = []
        ret.append("commit " + self.objid.hex())
        if self.parent:
            ret.append("parent " + self.parent.hex())
        if self.mergefrom:
            ret.append("merge " + self.mergefrom.hex())
        ret.append("auther " + self.author)
        ret.append("datetime " + datetime.fromtimestamp(self.createtime, timezone.utc).strftime("%Y-%m-%d %H:%M:%S"))
        ret.append("")
        ret.append(self.msg)
        return "\n".join(ret)

class GitTagObject:
    type = GitObjectType.tag
    def __init__(self, objid, raw):
        self.objid = objid
        self.raw = raw
        self.object = None
        self.type = None
        self.tag = None
        self.tagger = None
        self.createtime = None
        buf = StringIO(raw.decode())
        while True:
            line = buf.readline().strip()
            if line == "":
                break
            elif line.startswith("object "):
                self.object = bytes.fromhex(line[7:])
            elif line.startswith("type "):
                self.type = line[5:]
            elif line.startswith("tag "):
                self.tag = line[4:]
            elif line.startswith("tagger "):
                p = re.match("([a-zA-Z0-9_ ]+) <[^>]+> (\\d+) [0-9+-]+", line[7:])
                if p:
                    self.tagger = p[1]
                    self.createtime = int(p[2])

    def __str__(self):
        ret = []
        ret.append("tag " + self.objid.hex())
        ret.append("%s %s" % (self.type, self.object.hex()))
        ret.append("name " + self.tag)
        ret.append("creator " + self.tagger)
        ret.append("datetime " + datetime.fromtimestamp(self.createtime, timezone.utc).strftime("%Y-%m-%d %H:%M:%S"))
        return "\n".join(ret)

class GitTreeObject:
    type = GitObjectType.tree
    def __init__(self, objid, raw):
        self.objid = objid
        self.raw = raw
        self.rawlen = len(raw)
        self.children = {}
        cur = 0
        while cur < self.rawlen:
            end = raw.index(b'\x00', cur)
            (mode, filename) = raw[cur:end].decode().split(" ", 1)
            mode = int(mode, 8)
            sha1 = raw[end + 1:end + 21]
            cur = end + 21
            self.children[filename] = (mode, sha1)

    def __str__(self):
        ret = []
        for (filename, v) in self.children.items():
            ret.append("%6o %s %s" % (v[0], v[1].hex(), filename))
        return "\n".join(ret)

class GitBlobObject:
    type = GitObjectType.blob
    def __init__(self, objid, raw):
        self.objid = objid
        self.raw = raw


class GitRepo:

    def __init__(self, repo):
        self.objs = {}
        self.packfiles = []
        self.repo = repo
        self.branches = {}
        self.tags = {}
        self.header = None
        self.objstore = os.path.join(repo, "objects")
        for objectfile in glob.glob(os.path.join(self.objstore, "??", "*")):
            hashstr = objectfile[-41:-39] + objectfile[-38:]
            hashstr = bytes.fromhex(hashstr)
            self.objs[hashstr] = (0, -1)

        packidx = 0
        for idxfile in glob.glob(os.path.join(self.objstore, "pack", "*.idx")):
            self.loadobjidx(idxfile, packidx)
            packfile = idxfile[:-4] + ".pack"
            self.packfiles.append(open(packfile, "rb"))
            packidx += 1

        self.loadrefs()

    def loadrefs(self):
        packedrefs = os.path.join(self.repo, "packed-refs")
        if os.path.isfile(packedrefs):
            for line in open(packedrefs):
                m = re.match("([0-9a-z]+) (.+)", line)
                if m == None:
                    pass
                else:
                    objid = m[1]
                    if m[2].startswith("refs/remotes/origin/"):
                        name = m[2][len("refs/remotes/origin/"):]
                        self.tags[name] = bytes.fromhex(objid)
                    if m[2].startswith("refs/tags/"):
                        name = m[2][len("refs/tags/"):]
                        self.branches[name] = bytes.fromhex(objid)

            for filepath in glob.glob((os.path.join(self.repo, "refs", "heads", "**")), recursive=True):
                if os.path.isfile(filepath):
                    objid = open(filepath).readline().strip()
                    base = os.path.join(self.repo, "refs", "heads") + "\\"
                    name = filepath[len(base):].replace("\\", "/")
                    self.branches[name] = bytes.fromhex(objid)

            for filepath in glob.glob((os.path.join(self.repo, "refs", "remotes", "**")), recursive=True):
                if os.path.isfile(filepath):
                    if os.path.basename(filepath) == "HEAD":
                        pass
                    else:
                        objid = open(filepath).readline().strip()
                        base = os.path.join(self.repo, "refs", "remotes") + "\\"
                        name = filepath[len(base):].replace("\\", "/")
                        self.branches[name] = bytes.fromhex(objid)

            for filepath in glob.glob((os.path.join(self.repo, "refs", "tags", "**")), recursive=True):
                if os.path.isfile(filepath):
                    objid = open(filepath).readline().strip()
                    base = os.path.join(self.repo, "refs", "tags") + "\\"
                    name = filepath[len(base):].replace("\\", "/")
                    self.tags[name] = bytes.fromhex(objid)

    def loadobjidx(self, idxfile, packidx):
        buf = open(idxfile, "rb").read()
        if buf[0:4] != b'\xfftOc':
            raise "Invalid idx file: " + idxfile
        if buf[4:8] != b'\x00\x00\x00\x02':
            raise "Invalid idx file: " + idxfile
        objnum = unpack(">I", buf[1028:1032])[0]
        hasharray = 1032
        crcarray = hasharray + 20 * objnum
        offarray = crcarray + 4 * objnum
        loffarray = offarray + 4 * objnum
        for i in range(objnum):
            hashstr = buf[hasharray + i * 20:hasharray + i * 20 + 20]
            off = unpack(">I", buf[offarray + i * 4:offarray + i * 4 + 4])[0]
            if off & 0x80000000:
                loffidx = off & 0x7FFFFFFF
                off = unpack(">Q", buf[loffarray + loffidx * 8:loffarray + loffidx * 8 + 8])[0]
            self.objs[hashstr] = (
             off, packidx)

    def readnumber(self, fd):
        c = fd.read(1)[0]
        fshift = 7
        ret = c & 127
        while c & 128:
            c = fd.read(1)[0]
            ret += (c & 127) << fshift
            fshift += 7
        return ret

    def readnumber2(self, fd):
        c = fd.read(1)[0]
        ftype = c >> 4 & 7
        flen = c & 15
        fshift = 4
        while c & 128:
            c = fd.read(1)[0]
            flen = flen + ((c & 127) << fshift)
            fshift += 7
        return ftype, flen

    def decompress(self, fd, original_size):
        ret = []
        d = zlib.decompressobj()
        size_remain = original_size
        while size_remain>0:
            buf = fd.read(1024)
            outstr = d.decompress(buf)
            size_remain -= len(outstr)
            ret.append(outstr)

        return (b'').join(ret)

    def decompressdelta(self, base, delta):
        ret = []
        fd = BytesIO(delta)
        baselen = self.readnumber(fd)
        newlen = self.readnumber(fd)
        while True:
            cmd = fd.read(1)
            if cmd == b'':
                break
            else:
                cmd = cmd[0]
                if cmd & 128:
                    offset = 0
                    size = 0
                    if cmd & 1:
                        offset += fd.read(1)[0]
                    if cmd & 2:
                        offset += fd.read(1)[0] << 8
                    if cmd & 4:
                        offset += fd.read(1)[0] << 16
                    if cmd & 8:
                        offset += fd.read(1)[0] << 24
                    if cmd & 16:
                        size += fd.read(1)[0]
                    if cmd & 32:
                        size += fd.read(1)[0] << 8
                    if cmd & 64:
                        size += fd.read(1)[0] << 16
                    if size == 0:
                        size = 65536
                    ret.append(base[offset:offset + size])
                else:
                    ret.append(fd.read(cmd & 127))

        return (b'').join(ret)

    def readpackerobj(self, fd, off):
        fd.seek(off)
        ftype, flen = self.readnumber2(fd)
        ftype = GitObjectType(ftype)
        if ftype == GitObjectType.ofs_delta:
            c = fd.read(1)[0]
            ofs = c & 127
            while c & 128:
                c = fd.read(1)[0]
                ofs = (ofs << 7) + 128 + (c & 127)

            deltaraw = self.decompress(fd, flen)
            (base_type, baseraw) = self.readpackerobj(fd, off - ofs)
            return (base_type, self.decompressdelta(baseraw, deltaraw))
        if ftype == GitObjectType.ref_delta:
            ref = fd.read(20)
            deltaraw = self.decompress(fd, flen)
            baseobject = self.readobj(ref)
            base_type = baseobject.type
            return (base_type, self.decompressdelta(baseobject.raw, deltaraw))
        return (ftype, self.decompress(fd, flen))

    @lru_cache(maxsize=1000)
    def readobj(self, objid):
        if objid in self.objs:
            (off, idx) = self.objs[objid]
            if idx == -1:
                hexstr = objid.hex()
                objfile = os.path.join(self.objstore, hexstr[0:2], hexstr[2:])
                objraw = open(objfile, "rb").read()
                objraw = zlib.decompress(objraw)
                hdrlen = objraw.index(b'\x00')
                headers = objraw[:hdrlen].decode().split(" ")
                ftype = headers[0]
                flen = int(headers[1])
                objraw = objraw[hdrlen + 1:hdrlen + 1 + flen]
                ftype = GitObjectType[ftype]
            else:
                fd = self.packfiles[idx]
                (ftype, objraw) = self.readpackerobj(fd, off)
            if ftype == GitObjectType.commit:
                return GitCommitObject(objid, objraw)
            if ftype == GitObjectType.tree:
                return GitTreeObject(objid, objraw)
            if ftype == GitObjectType.blob:
                return GitBlobObject(objid, objraw)
            if ftype == GitObjectType.tag:
                return GitTagObject(objid, objraw)

    def list_commits(self, branch, parent=None):
        parentset = {}
        if parent:
            commits = self.list_commits(parent)
            parentset = {c.objid for c in commits}
        ret = []
        if branch in self.branches:
            commitid = self.branches[branch]
        elif branch in self.tags:
            commitid = self.tags[branch]
        else:
            return ret
        
        while commitid:
            commitobj = self.readobj(commitid)
            commitid = commitobj.parent
            ret.append(commitobj)
            if commitid in parentset:
                break

        for i in range(len(ret)):
            ret[i].seq = i

        return ret

    def find_fileobj_id(self, roottreeid, path):
        treeid = roottreeid
        for sep in path.split("/"):
            tree = self.readobj(treeid)
            if tree == None:
                return None
            if sep in tree.children:
                treeid = tree.children[sep][1]
            else:
                return None

        return treeid

    def list_file_history(self, commitid, filepath):
        revs = []
        while commitid:
            commit = self.readobj(commitid)
            if not commit:
                break
            else:
                fileid = self.find_fileobj_id(commit.tree, filepath)
                if fileid == None:
                    break
                if len(revs) == 0:
                    revs.append([commit, fileid])
                elif revs[-1][1] == fileid:
                    revs[-1][0] = commit
                else:
                    revs.append([commit, fileid])
                commitid = commit.parent

        ret = [DiffObject(revs[i][0].objid, filepath, "*", revs[i + 1][1], revs[i][1]) for i in range(len(revs) - 1)]
        ret.append(DiffObject(revs[-1][0].objid, filepath, "+", None, revs[-1][1]))
        return ret

    def compare_trees(self, oldtreeid, newtreeid):
        diff = []
        if oldtreeid:
            tree1 = self.readobj(oldtreeid).children
            tree1folders = set([f for f in tree1.keys() if tree1[f][0] == 16384])
            tree1files = set([f for f in tree1.keys() if tree1[f][0] != 16384])
        else:
            tree1folders = set()
            tree1files = set()
        if newtreeid:
            tree2 = self.readobj(newtreeid).children
            tree2folders = set([f for f in tree2.keys() if tree2[f][0] == 16384])
            tree2files = set([f for f in tree2.keys() if tree2[f][0] != 16384])
        else:
            tree2folders = set()
            tree2files = set()
        for filename in tree1files & tree2files:
            if tree1[filename][1] != tree2[filename][1]:
                diff.append(DiffObject(0, filename, "*", tree1[filename][1], tree2[filename][1]))

        for filename in tree1files - tree2files:
            diff.append(DiffObject(0, filename, "-", tree1[filename][1], None))

        for filename in tree2files - tree1files:
            diff.append(DiffObject(0, filename, "+", None, tree2[filename][1]))

        for filename in tree1folders & tree2folders:
            if tree1[filename][1] != tree2[filename][1]:
                subdiff = self.compare_trees(tree1[filename][1], tree2[filename][1])
                for e in subdiff:
                    e.filepath = filename + "/" + e.filepath
                    diff.append(e)

        for filename in tree1folders - tree2folders:
            subdiff = self.compare_trees(tree1[filename][1], None)
            for e in subdiff:
                e.filepath = filename + "/" + e.filepath
                diff.append(e)

        for filename in tree2folders - tree1folders:
            subdiff = self.compare_trees(None, tree2[filename][1])
            for e in subdiff:
                e.filepath = filename + "/" + e.filepath
                diff.append(e)
        return diff

    def compare_commits(self, oldcommitid, newcommitid):
        oldtree = self.readobj(oldcommitid).tree if oldcommitid else None
        newtree = self.readobj(newcommitid).tree if newcommitid else None
        diffs = self.compare_trees(oldtree, newtree)
        for diff in diffs:
            diff.commitid = newcommitid

        diffs = sorted(diffs, key=(lambda x: x.filepath))
        return diffs

    def compare_commit_with_prev(self, commitid):
        commitobj = self.readobj(commitid)
        newtree = commitobj.tree
        oldtree = self.readobj(commitobj.parent).tree if commitobj.parent else None
        diffs = self.compare_trees(oldtree, newtree)
        for diff in diffs:
            diff.commitid = commitid

        diffs = sorted(diffs, key=(lambda x: x.filepath))
        return diffs

    def getobjtyperapid(self, objid, packfd=None, packoff=None):
        if objid in self.objs:
            (off, idx) = self.objs[objid]
            if idx == -1:
                hexstr = objid.hex()
                objfile = os.path.join(self.objstore, hexstr[0:2], hexstr[2:])
                fd = open(objfile, "rb")
                headerline = self.decompress(fd, 8)
                fd.close()
                if headerline.startswith(b"commit"):
                    return GitObjectType.commit
                elif headerline.startswith(b"tree"):
                    return GitObjectType.tree
                elif headerline.startswith(b"tag"):
                    return GitObjectType.tag
                elif headerline.startswith(b"blob"):
                    return GitObjectType.blob
            else:
                if packfd:
                    fd = packfd
                    off = packoff
                else:
                    fd = self.packfiles[idx]
                fd.seek(off)
                ftype, flen = self.readnumber2(fd)
                ftype = GitObjectType(ftype)
                if ftype == GitObjectType.ofs_delta:
                    c = fd.read(1)[0]
                    ofs = c & 127
                    while c & 128:
                        c = fd.read(1)[0]
                        ofs = (ofs << 7) + 128 + (c & 127)
                    return self.getobjtyperapid(objid, fd, off - ofs)
                elif ftype == GitObjectType.ref_delta:
                    ref = fd.read(20)
                    return self.getobjtyperapid(ref)
                else:
                    return ftype

    def itercommitobjs(self):
        for i in range(0, len(self.packfiles)):
            offs = [(v[0], k) for k,v in self.objs.items() if v[1]==i]
            offs = sorted(offs)
            fd = self.packfiles[i]
            for off, objid in offs:
                ftype = self.getobjtyperapid(objid)
                if ftype == GitObjectType.commit:
                    yield self.readobj(objid)

        for objid in [k for k,v in self.objs.items() if v[1]==-1]:
            hexstr = objid.hex()
            objfile = os.path.join(self.objstore, hexstr[0:2], hexstr[2:])
            fd = open(objfile, "rb")
            headerline = self.decompress(fd, 8)
            fd.close()
            if headerline.startswith(b"commit"):
                yield self.readobj(objid)

if __name__ == "__main__":
    git = GitRepo("D:\\github\\Mindustry\\.git")
    git.readobj(bytes.fromhex("d65f226b3ae5eebe7439f83c7d213284d6159cfe"))
    commits = list(git.itercommitobjs())
    print(len(commits))
