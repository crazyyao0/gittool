import tkinter as tk
from tkinter import filedialog
from tkinter import messagebox
from tkinter import ttk
from tkinter.scrolledtext import ScrolledText
from gittool import GitRepo
import os, subprocess
from datetime import datetime
import time
DIFFTOOL = "D:\\vscode\\workspace\\gittool\\windiff.exe"
EDITTOOL = "C:\\Program Files\\EditPlus 3\\editplus.exe"
MERGETOOL = "C:\\Program Files\\Perforce\\p4merge.exe"
GITCMD = "git.exe"

class BaseWnd:
    def ShowDialog(self, typeobj):
        popup = tk.Toplevel(self.top)
        wnd = typeobj(popup)
        popup.focus_force()
        popup.grab_set()
        return wnd

    def ShowDiff(self, file1id, file2id, basename):
        if file1id:
            obj = self.repo.readobj(file1id)
            filename1 = file1id.hex()[0:8] + "_" + basename
            open(filename1, "wb").write(obj.raw)
        else:
            file1id = bytes.fromhex("0000000000000000000000000000000000000000")
            filename1 = file1id.hex()[0:8] + "_" + basename
            open(filename1, "wb")
        if file2id:
            obj = self.repo.readobj(file2id)
            filename2 = file2id.hex()[0:8] + "_" + basename
            open(filename2, "wb").write(obj.raw)
        else:
            file2id = bytes.fromhex("0000000000000000000000000000000000000000")
            filename2 = file2id.hex()[0:8] + "_" + basename
            open(filename2, "wb")
        args = [DIFFTOOL, filename1, filename2]
        subprocess.check_call(args)
        os.remove(filename1)
        os.remove(filename2)

    def ViewFile(self, file1id, basename):
        obj = self.repo.readobj(file1id)
        filename1 = file1id.hex()[0:8] + "_" + basename
        open(filename1, "wb").write(obj.raw)
        args = [EDITTOOL, filename1]
        subprocess.check_call(args)
        os.remove(filename1)

    def FormatTime(self, utc):
        ltime = datetime.fromtimestamp(utc)
        return ltime.strftime("%Y-%m-%d %H:%M:%S")

    def FormatComments(self, commit):
        comments = [m.strip() for m in commit.msg.split("\n") if m.strip()]
        if len(comments) > 1:
            if comments[0].startswith("Merge branch"):
                del comments[0]
        if len(comments) > 1:
            if comments[-1].startswith("See merge request"):
                del comments[-1]
        comments = "\\n".join(comments)
        return comments

class CommitDetailWnd(BaseWnd):

    def __init__(self, top):
        self.top = top
        self.frame1 = ttk.Frame(top)
        self.frame1.pack(side="top", fill="x")
        self.txtInfo = ScrolledText(self.frame1)
        self.txtInfo.configure(height=10)
        self.txtInfo.pack(fill="both", expand=1)
        self.frame2 = ttk.Frame(top)
        self.frame2.pack(side="top", expand=1, fill="both")
        self.treeview1 = ttk.Treeview(self.frame2)
        self.scroll1 = ttk.Scrollbar((self.frame2), command=(self.treeview1.yview))
        self.scroll1.pack(side="right", fill="y")
        self.treeview1.configure(yscrollcommand=(self.scroll1.set))
        self.treeview1["columns"] = "1"
        self.treeview1.pack(side="right", expand=1, fill="both")
        self.treeview1.column("#0", width=70, stretch=0)
        self.treeview1.column("1", width=500, stretch=0)
        self.treeview1.heading("#0", text="method", anchor="w")
        self.treeview1.heading("1", text="filename", anchor="w")
        self.treeview1.bind("<Button-3>", self.On_treeView1_rightclicked)
        self.treeview1.bind("<Double-1>", self.On_treeView1_doubleclicked)
        self.treeview1menu = tk.Menu(top, tearoff=0)
        self.treeview1menu.add_command(label="Show diff", command=(self.On_treeView1_showDiffs))
        self.treeview1menu.add_command(label="View file", command=(self.On_treeView1_viewfile))
        self.treeview1menu.add_command(label="View file history", command=(self.On_treeView1_viewFileHistory))

    def showchanges(self, repo, diffs):
        self.repo = repo
        self.diffs = diffs
        commits = set()
        for diff in self.diffs:
            self.treeview1.insert("", "end", text=(diff.method), values=(diff.filepath))
            commits.add(diff.commitid)

        messages = []
        for commitid in commits:
            commit = self.repo.readobj(commitid)
            createtime = datetime.utcfromtimestamp(commit.createtime).strftime("%Y-%m-%d %H:%M:%S")
            comments = ["  " + m for m in commit.msg.split("\n") if m]
            messages.append("%s %s %s" % (commitid.hex(), createtime, commit.author))
            messages += comments
            messages.append("")

        self.txtInfo.insert("end", "\n".join(messages))
        self.txtInfo.configure(state="disabled")

    def On_treeView1_rightclicked(self, event):
        iid = self.treeview1.identify_row(event.y)
        if iid:
            self.treeview1.selection_set(iid)
            self.selected_idx = self.treeview1.index(iid)
            self.treeview1menu.post(event.x_root, event.y_root)

    def On_treeView1_doubleclicked(self, event):
        iid = self.treeview1.identify_row(event.y)
        if iid:
            self.selected_idx = self.treeview1.index(iid)
            self.On_treeView1_showDiffs()

    def On_treeView1_viewfile(self):
        diffobj = self.diffs[self.selected_idx]
        self.ViewFile(diffobj.fileid2, os.path.basename(diffobj.filepath))

    def On_treeView1_showDiffs(self):
        diffobj = self.diffs[self.selected_idx]
        self.ShowDiff(diffobj.fileid1, diffobj.fileid2, os.path.basename(diffobj.filepath))

    def On_treeView1_viewFileHistory(self):
        diffobj = self.diffs[self.selected_idx]
        wnd = self.ShowDialog(ViewFileHistoryWnd)
        wnd.showhistory(self.repo, diffobj.commitid, diffobj.filepath)


class CompareWithDlg(BaseWnd):

    def __init__(self, top):
        self.top = top
        top.title("Compare with dialog")
        self.frame1 = ttk.Frame(top)
        self.frame1.pack(side="top", fill="x")
        self.label1 = ttk.Label(self.frame1)
        self.label1.configure(text="Please input commitid/branch name/tag name")
        self.label1.pack(side="left")
        self.frame2 = ttk.Frame(top)
        self.frame2.pack(side="top", fill="x")
        self.comboInput = ttk.Combobox(self.frame2)
        self.comboInput.pack(side="left", expand=1, fill="x")
        self.frame3 = ttk.Frame(top)
        self.frame3.pack(side="top", fill="x")
        self.btnCancel = ttk.Button((self.frame3), command=(self.top.destroy))
        self.btnCancel.configure(text="Cancel")
        self.btnCancel.pack(side="right")
        self.btnOK = ttk.Button((self.frame3), command=(self.On_btnOK_Click))
        self.btnOK.configure(text="OK")
        self.btnOK.pack(side="right")

    def showdialog(self, repo, callback):
        self.repo = repo
        self.callback = callback
        branches = sorted(list(self.repo.branches) + list(self.repo.tags))
        self.comboInput.configure(values=branches)

    def On_btnOK_Click(self):
        idx = self.comboInput.current()
        if idx >= 0:
            name = self.comboInput.get()
            if name in self.repo.branches:
                commitid = self.repo.branches[name]
            elif name in self.repo.tags:
                commitid = self.repo.tags[name]
        else:
            name = self.comboInput.get()
            commitid = bytes.fromhex(name)
        self.callback(commitid)
        self.top.destroy()


class ViewFileHistoryWnd(BaseWnd):

    def __init__(self, top):
        self.top = top
        self.treeview1 = ttk.Treeview(self.top)
        self.scroll1 = ttk.Scrollbar((self.top), command=(self.treeview1.yview))
        self.treeview1.configure(yscrollcommand=(self.scroll1.set), height=25)
        self.treeview1["columns"] = ('1', '2', '3')
        self.treeview1.column("#0", width=270, stretch=0)
        self.treeview1.column("1", width=130, stretch=0)
        self.treeview1.column("2", width=100, stretch=0)
        self.treeview1.column("3", width=400)
        self.treeview1.heading("#0", text="CommitID", anchor="w")
        self.treeview1.heading("1", text="Date", anchor="w")
        self.treeview1.heading("2", text="Name", anchor="w")
        self.treeview1.heading("3", text="Comments", anchor="w")
        self.treeview1.bind("<Button-3>", self.On_treeView1_rightclicked)
        self.treeview1.bind("<Double-1>", self.On_treeView1_doubleclicked)
        self.scroll1.pack(side="right", fill="y")
        self.treeview1.pack(side="right", expand=1, fill="both")
        self.treeview1menu = tk.Menu(top, tearoff=0)
        self.treeview1menu.add_command(label="Compare with prev", command=(self.On_treeView1_compareWithPrev))
        self.treeview1menu.add_command(label="View file", command=(self.On_treeView1_viewFile))

    def showhistory(self, repo, commitid, filepath):
        self.repo = repo
        self.histories = self.repo.list_file_history(commitid, filepath)
        for item in self.histories:
            commit = self.repo.readobj(item.commitid)
            createtime = self.FormatTime(commit.createtime)
            comments = [m for m in commit.msg.split("\n") if m]
            if len(comments) >= 3:
                comments = comments[1:-1]
            comments = ";".join(comments)
            self.treeview1.insert("", "end", text=(commit.objid.hex()), values=(createtime, commit.author, comments))

    def On_treeView1_rightclicked(self, event):
        iid = self.treeview1.identify_row(event.y)
        if iid:
            self.selected_idx = self.treeview1.index(iid)
            self.treeview1menu.post(event.x_root, event.y_root)

    def On_treeView1_viewFile(self):
        diffitem = self.histories[self.selected_idx]
        self.ViewFile(diffitem.fileid2, os.path.basename(diffitem.filepath))

    def On_treeView1_compareWithPrev(self):
        diffitem = self.histories[self.selected_idx]
        self.ShowDiff(diffitem.fileid1, diffitem.fileid2, os.path.basename(diffitem.filepath))

    def On_treeView1_doubleclicked(self, event):
        iid = self.treeview1.identify_row(event.y)
        if iid:
            self.selected_idx = self.treeview1.index(iid)
            self.On_treeView1_compareWithPrev()


class ViewFilesWnd(BaseWnd):

    def __init__(self, top):
        self.top = top
        self.treeview1 = ttk.Treeview(self.top)
        self.scroll1 = ttk.Scrollbar((self.top), command=(self.treeview1.yview))
        self.treeview1.configure(yscrollcommand=(self.scroll1.set), height=25)
        self.treeview1["columns"] = ('1', '2')
        self.treeview1.column("#0", width=300, stretch=0)
        self.treeview1.column("1", width=100, stretch=0)
        self.treeview1.column("2", width=400, stretch=0)
        self.treeview1.heading("#0", text="filename", anchor="w")
        self.treeview1.heading("1", text="mode", anchor="w")
        self.treeview1.heading("1", text="fileid", anchor="w")
        self.treeview1.bind("<Button-3>", self.On_treeView1_rightclicked)
        self.treeview1.bind("<Double-1>", self.On_treeView1_doubleclicked)
        self.scroll1.pack(side="right", fill="y")
        self.treeview1.pack(side="right", expand=1, fill="both")
        self.treeview1menu = tk.Menu(top, tearoff=0)
        self.treeview1menu.add_command(label="View file", command=(self.On_treeView1_viewFile))
        self.treeview1menu.add_command(label="View file history", command=(self.On_treeView1_viewFileHistory))

    def expandtree(self, treeid, treeviewobj, path):
        treeobj = self.repo.readobj(treeid)
        for name in treeobj.children:
            (mode, objid) = treeobj.children[name]
            treeid = self.treeview1.insert(treeviewobj, "end", text=name, values=("%06o" % mode, objid.hex(), path + name))
            if mode == 16384:
                self.expandtree(objid, treeid, path + name + "/")

    def showFiles(self, repo, commitid):
        self.repo = repo
        self.commitid = commitid
        commit = self.repo.readobj(commitid)
        self.expandtree(commit.tree, "", "")

    def On_treeView1_rightclicked(self, event):
        iid = self.treeview1.identify_row(event.y)
        if iid:
            self.treeview1.selection_set(iid)
            self.selected_item = self.treeview1.item(iid)["values"]
            self.treeview1menu.post(event.x_root, event.y_root)

    def On_treeView1_doubleclicked(self, event):
        iid = self.treeview1.identify_row(event.y)
        if iid:
            self.selected_item = self.treeview1.item(iid)["values"]
            self.On_treeView1_viewFile()

    def On_treeView1_viewFile(self):
        if self.selected_item:
            if self.selected_item[0] != 40000:
                file1id = bytes.fromhex(self.selected_item[1])
                self.ViewFile(file1id, os.path.basename(self.selected_item[2]))

    def On_treeView1_viewFileHistory(self):
        wnd = self.ShowDialog(ViewFileHistoryWnd)
        wnd.showhistory(self.repo, self.commitid, self.selected_item[2])


class AppMainWnd(BaseWnd):

    def __init__(self, top):
        self.top = top
        top.title("Git Tool")
        self.upperpannel = ttk.Frame(top)
        self.upperpannel.pack(side="top", pady=(0, 2), expand=False, fill="x")
        self.btnOpen = ttk.Button((self.upperpannel), command=(self.On_btnOpen_click))
        self.btnOpen.configure(text="Open")
        self.btnOpen.pack(side="left")
        self.label1 = ttk.Label(self.upperpannel)
        self.label1.configure(text="Please open a git storage first")
        self.label1.pack(side="left")
        self.btnRefresh = ttk.Button((self.upperpannel), command=(self.On_btnRefresh_click))
        self.btnRefresh.configure(text="Pull and refresh")
        self.btnRefresh.pack(side="right")
        self.branchpannel = ttk.Frame(top)
        self.branchpannel.pack(side="top", pady=(0, 2), expand=False, fill="x")
        self.label2 = ttk.Label(self.branchpannel)
        self.label2.configure(text="Select a branch or tag:")
        self.label2.pack(side="left")
        self.comboBranch = ttk.Combobox((self.branchpannel), width=40)
        self.comboBranch.configure()
        self.comboBranch.pack(side="left", padx=(0, 10))
        self.comboBranch.bind("<<ComboboxSelected>>", self.On_comboBranch_selected)
        self.comboBranch.bind('<KeyRelease>', self.On_comboBranch_KeyReleased)
        self.comboBranch.bind('<Return>', self.On_comboBranch_EnterKeyPressed)
        self.label3 = ttk.Label(self.branchpannel)
        self.label3.configure(text="Select parent branch:")
        self.label3.pack(side="left")
        self.comboParentBranch = ttk.Combobox((self.branchpannel), width=40)
        self.comboParentBranch.configure(state="readonly")
        self.comboParentBranch.pack(side="left", padx=(0, 10))
        self.comboParentBranch.bind("<<ComboboxSelected>>", self.On_comboBranch_selected)
        self.querypannel = ttk.Frame(top)
        self.querypannel.pack(side="top", pady=(0, 2), expand=False, fill="x")
        self.label5 = ttk.Label(self.querypannel)
        self.label5.configure(text="Quick Search:")
        self.label5.pack(side="left")
        self.txtCommitid = ttk.Entry(self.querypannel)
        self.txtCommitid.configure(width=64)
        self.txtCommitid.pack(side="left", padx=(0, 10))
        self.txtCommitid.bind("<Return>", self.On_txtCommitid)
        self.label4 = ttk.Label(self.querypannel)
        self.label4.configure(text="Select committer:")
        self.label4.pack(side="left")
        self.comboCommitter = ttk.Combobox(self.querypannel)
        self.comboCommitter.configure(state="readonly")
        self.comboCommitter.pack(side="left", padx=(0, 10))
        self.comboCommitter.bind("<<ComboboxSelected>>", self.On_comboBranch_selected)
        self.mainpannel = ttk.Frame(top)
        self.mainpannel.configure(borderwidth=2)
        self.mainpannel.pack(side="top", expand=True, fill="both")
        self.treeview1 = ttk.Treeview(self.mainpannel)
        self.scroll1 = ttk.Scrollbar((self.mainpannel), command=(self.treeview1.yview))
        self.scroll1.pack(side="right", fill="y")
        self.treeview1.configure(yscrollcommand=(self.scroll1.set))
        self.treeview1["columns"] = ('1', '2', '3')
        self.treeview1.pack(side="right", expand=1, fill="both")
        self.treeview1.column("#0", width=270, stretch=0)
        self.treeview1.column("1", width=130, stretch=0)
        self.treeview1.column("2", width=100, stretch=0)
        self.treeview1.column("3", width=400)
        self.treeview1.heading("#0", text="CommitID", anchor="w")
        self.treeview1.heading("1", text="Date", anchor="w")
        self.treeview1.heading("2", text="Name", anchor="w")
        self.treeview1.heading("3", text="Comments", anchor="w")
        self.treeview1.bind("<Button-3>", self.On_treeView1_rightclicked)
        self.treeview1.bind("<Double-1>", self.On_treeView1_doubleclicked)
        self.treeview1.bind("<Control-c>", self.On_treeView1_ctrlc)
        self.treeview1menu = tk.Menu(top, tearoff=0)
        self.treeview1menu.add_command(label="Compare with prev", command=(self.On_treeView1menu_compareWithPrev))
        self.treeview1menu.add_command(label="Compare with...", command=(self.On_treeView1menu_compareWith))
        self.treeview1menu.add_command(label="View files", command=(self.On_treeView1menu_viewFiles))
        self.treeview1menu.add_command(label="Copy commit ID", command=(self.On_treeView1menu_copyCommitID))

    def On_treeView1_ctrlc(self, args):
        lines = []
        for iid in self.treeview1.selection():
            item = self.treeview1.item(iid)
            lines.append("\t".join([item["text"]] + item["values"]))

        self.top.clipboard_clear()
        self.top.clipboard_append("\n".join(lines))

    def ReloadAll(self):
        self.label1.configure(text=(self.folderpath))
        self.repo = GitRepo(self.folderpath)
        self.comboBranch.configure(values=(list(self.repo.branches) + list(self.repo.tags)))
        self.comboBranch.set("")
        self.branches2 = ["N/A"] + list(self.repo.branches)
        self.comboParentBranch.configure(values=(self.branches2))
        self.comboParentBranch.set("")
        self.comboCommitter.configure(values=[])
        self.comboCommitter.set("")
        (self.treeview1.delete)(*self.treeview1.get_children())

    def On_txtCommitid(self, event):
        if self.commits == 0:
            return
        tosearch = self.txtCommitid.get()
        if len(tosearch) < 2:
            return
        selections = []
        for iid in self.treeview1.get_children():
            item = self.treeview1.item(iid)
            if not tosearch in item["text"]:
                if tosearch in item["values"][2]:
                    pass
            selections.append(iid)

        if len(selections) > 0:
            self.treeview1.selection_set(selections)
            self.treeview1.see(selections[0])

    def On_btnOpen_click(self):
        folderpath = filedialog.askdirectory()
        if os.path.basename(folderpath) != ".git":
            folderpath = os.path.join(folderpath, ".git")
        if not os.path.isdir(folderpath):
            messagebox.showerror("Error", "The selected path is not a git repository")
            self.label1.configure(text="The selected path is not a git repository")
            return
        self.folderpath = folderpath
        self.ReloadAll()

    def On_btnRefresh_click(self):
        msg = subprocess.check_output([GITCMD, "pull"], cwd=(self.folderpath[:-5]))
        messagebox.showinfo("Information", msg)
        self.ReloadAll()

    def On_comboBranch_KeyReleased(self, event):
        filter = self.comboBranch.get()
        all_items = list(self.repo.branches) + list(self.repo.tags)
        filtered_items = [item for item in all_items if filter.lower() in item.lower()]
        self.comboBranch["values"] = filtered_items
    
    def On_comboBranch_EnterKeyPressed(self, event):
        filter = self.comboBranch.get()
        all_items = list(self.repo.branches) + list(self.repo.tags)
        filtered_items = [item for item in all_items if filter.lower() in item.lower()]
        if len(filtered_items) == 1:
            self.comboBranch.set(filtered_items[0])
            self.comboBranch.event_generate("<<ComboboxSelected>>")
        else:
            self.comboBranch.event_generate('<Down>')

    def On_comboBranch_selected(self, event):
        if self.comboBranch.current() < 0:
            return
        branchname = self.comboBranch.get()
        basename = None
        if self.comboParentBranch.current() > 0:
            basename = self.comboParentBranch.get()
        committer = set()
        self.commits = self.repo.list_commits(branchname, basename)
        for commit in self.commits:
            committer.add(commit.author)

        self.comboCommitter.configure(values=(["ALL"] + sorted(list(committer))))
        committerfilter = "ALL"
        if self.comboCommitter.current() > 0:
            committerfilter = self.comboCommitter.get()
        (self.treeview1.delete)(*self.treeview1.get_children())
        for commit in self.commits:
            if not committerfilter == "ALL":
                if committerfilter == commit.author:
                    pass
            createtime = self.FormatTime(commit.createtime)
            comments = self.FormatComments(commit)
            self.treeview1.insert("", "end", text=(commit.objid.hex()), values=(createtime, commit.author + ("/" + commit.committer if commit.committer else ""), comments))

    def On_treeView1_rightclicked(self, event):
        iid = self.treeview1.identify_row(event.y)
        if iid:
            self.treeview1.selection_set(iid)
            self.selected_item = self.treeview1.item(iid)["text"]
            self.treeview1menu.post(event.x_root, event.y_root)

    def On_treeView1_doubleclicked(self, event):
        iid = self.treeview1.identify_row(event.y)
        if iid:
            self.selected_item = self.treeview1.item(iid)["text"]
            self.On_treeView1menu_compareWithPrev()

    def On_treeView1menu_compareWithPrev(self):
        wnd = self.ShowDialog(CommitDetailWnd)
        commitid = bytes.fromhex(self.selected_item)
        diffs = self.repo.compare_commit_with_prev(commitid)
        wnd.showchanges(self.repo, diffs)

    def On_treeView1menu_compareWith(self):
        wnd = self.ShowDialog(CompareWithDlg)
        wnd.showdialog(self.repo, self.On_CompareWith_selected)

    def On_CompareWith_selected(self, commitid):
        selectedid = bytes.fromhex(self.selected_item)
        diffs = self.repo.compare_commits(commitid, selectedid)
        wnd = self.ShowDialog(CommitDetailWnd)
        wnd.showchanges(self.repo, diffs)

    def On_treeView1menu_viewFiles(self):
        commitid = bytes.fromhex(self.selected_item)
        wnd = self.ShowDialog(ViewFilesWnd)
        wnd.showFiles(self.repo, commitid)

    def On_treeView1menu_copyCommitID(self):
        commitid = self.selected_item
        self.top.clipboard_clear()
        self.top.clipboard_append(commitid)


if __name__ == "__main__":
    root = tk.Tk()
    root.geometry("800x600")
    top = AppMainWnd(root)
    root.mainloop()
