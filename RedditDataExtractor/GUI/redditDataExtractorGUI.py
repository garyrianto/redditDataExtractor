import os

from PyQt4.Qt import (QInputDialog, QObject, pyqtSignal, pyqtSlot, QListView, Qt, QLineEdit, QMessageBox, QMainWindow,
    QThread, QFileDialog, QTextCursor, QDialog)

from .redditDataExtractorGUI_auto import Ui_RddtDataExtractorMainWindow
from .settingsGUI import SettingsGUI
from .GUIFuncs import confirmDialog
from .downloadedPostsGUI import DownloadedPostsGUI
from .listModel import ListModel
from .genericListModelObjects import GenericListModelObj, User, Subreddit
from ..redditDataExtractor import DownloadType, ListType
from ..downloader import Downloader


def isNumber(s):
    try:
        float(s)
        return True
    except ValueError:
        return False


class Validator(QObject):
    finished = pyqtSignal(list)
    invalid = pyqtSignal(str)

    def __init__(self, rddtDataExtractor, queue, data, listType):
        super().__init__()
        self.rddtDataExtractor = rddtDataExtractor
        self.queue = queue
        self.data = data
        self.listType = listType
        self.valid = []

    @pyqtSlot()
    def run(self):
        if self.listType == ListType.USER:
            s = "user "
            validateFunc = self.rddtDataExtractor.getRedditor
        else:
            s = "subreddit "
            validateFunc = self.rddtDataExtractor.getSubreddit
        for d in self.data:
            name = d.name
            self.queue.put("Validating " + s + name + "\n")
            validatedData = validateFunc(name)
            if validatedData is None:
                self.invalid.emit(name)
            else:
                self.valid.append((d, validatedData))
        self.finished.emit(self.valid)


class listViewAndChooser(QListView):
    def __init__(self, gui, lstChooser, chooserDict, defaultLstName, classToUse, name):
        super().__init__(gui.centralwidget)
        self.setContextMenuPolicy(Qt.ActionsContextMenu)
        self.setObjectName(name)
        self.lstChooser = lstChooser
        self.chooserDict = chooserDict
        self.defaultLstName = defaultLstName
        self.classToUse = classToUse
        self.gui = gui
        self.rddtDataExtractor = self.gui.rddtDataExtractor

        for lstKey in self.chooserDict:
            print("Adding to chooser: " + str(lstKey))
            self.lstChooser.addItem(lstKey)
        print("default list: " + str(defaultLstName))
        model = chooserDict.get(defaultLstName)
        self.setModel(model)
        index = self.lstChooser.findText(defaultLstName)
        self.lstChooser.setCurrentIndex(index)

    def getCurrentSelectedIndex(self):
        # indices is a list of QModelIndex. Use selectedIndexes() rather than currentIndex() to make sure
        # something is actually selected. currentIndex() returns the top item if nothing is selected
        # - behavior we don't want.
        indices = self.selectedIndexes()
        index = None
        if len(indices) > 0:
            index = indices[0]  # only one thing should be selectable at a time
        return index

    def addToList(self):
        model = self.model()
        if model is not None:
            model.insertRows(model.rowCount(), 1)
            self.gui.setUnsavedChanges(True)

    def deleteFromList(self):
        model = self.model()
        index = self.getCurrentSelectedIndex()
        if model is not None and index is not None:
            row = index.row()
            model.removeRows(row, 1)
            self.gui.setUnsavedChanges(True)

    def makeNewList(self):
        listName, okay = QInputDialog.getText(QInputDialog(), self.objectName().capitalize() + " List Name",
                                              "New " + self.objectName().capitalize() + " List Name:",
                                              QLineEdit.Normal, "New " + self.objectName().capitalize() + " List")
        if okay and len(listName) > 0:
            if any([listName in lst for lst in self.rddtDataExtractor.subredditLists]):
                QMessageBox.information(QMessageBox(), "Reddit Data Extractor",
                                        "Duplicate subreddit list names not allowed.")
                return
            self.lstChooser.addItem(listName)
            self.lstChooser.setCurrentIndex(self.lstChooser.count() - 1)
            self.chooserDict[listName] = ListModel([], self.classToUse)
            self.chooseNewList(self.lstChooser.count() - 1)
            if self.rddtDataExtractor.defaultSubredditListName is None:  # becomes None if user deletes all subreddit lists
                self.rddtDataExtractor.defaultSubredditListName = listName
            self.gui.setUnsavedChanges(True)

    def viewDownloadedPosts(self):
        model = self.model()
        index = self.getCurrentSelectedIndex()
        if model is not None and index is not None:
            selected = model.getObjectInLst(index)
            downloadedPosts = selected.redditPosts
            if downloadedPosts is not None and len(downloadedPosts) > 0:
                downloadedPostsGUI = DownloadedPostsGUI(selected, self.model(), confirmDialog, self.gui.saveState)
                downloadedPostsGUI.exec_()
            else:
                QMessageBox.information(QMessageBox(), "Reddit Data Extractor",
                                        selected.name + " has no downloaded posts. Download some by hitting the download button.")
        elif index is None:
            QMessageBox.information(QMessageBox(), "Reddit Data Extractor",
                                    "To view a " + self.objectName() + "'s downloaded posts, please select a " + self.objectName() + " in the " + self.objectName() + " list.")


class userListViewAndChooser(listViewAndChooser):
    def __init__(self, gui):
        super().__init__(gui, gui.userListChooser, gui.rddtDataExtractor.userLists,
                         gui.rddtDataExtractor.defaultUserListName, User, "user")
        self.rddtDataExtractor.currentUserListName = self.defaultLstName

    def chooseNewList(self, listIndex):
        listName = self.lstChooser.itemText(listIndex)
        print("Choosing new list: " + listName)
        self.rddtDataExtractor.currentUserListName = listName
        model = self.chooserDict.get(listName)
        self.setModel(model)

    def removeNonDefaultLst(self):
        self.rddtDataExtractor.currentUserListName = self.rddtDataExtractor.defaultUserListName
        name = self.rddtDataExtractor.currentUserListName
        index = self.lstChooser.findText(name)
        self.lstChooser.setCurrentIndex(index)
        self.chooseNewList(index)

    def removeDefaultLst(self):
        modelName = list(self.chooserDict)[0]
        self.rddtDataExtractor.currentUserListName = modelName
        self.rddtDataExtractor.defaultUserListName = modelName
        index = self.lstChooser.findText(modelName)
        self.lstChooser.setCurrentIndex(index)
        self.chooseNewList(index)

    def removeLastLst(self):
        print('deleting last list')
        self.rddtDataExtractor.currentUserListName = None
        self.rddtDataExtractor.defaultUserListName = None
        self.setModel(ListModel([], GenericListModelObj))

    def removeLst(self):
        name = self.lstChooser.currentText()
        if len(name) <= 0:
            return
        msgBox = confirmDialog("Are you sure you want to delete the " + self.objectName() + " list: " + name + "?")
        ret = msgBox.exec_()
        if ret == QMessageBox.Yes:
            if len(self.chooserDict) <= 0:
                QMessageBox.information(QMessageBox(), "Reddit Data Extractor",
                                        "There are no more lists left to delete.")
                return
            self.lstChooser.removeItem(self.lstChooser.currentIndex())
            del self.chooserDict[name]
            defaultName = self.rddtDataExtractor.defaultUserListName
            # if default is not being removed, just remove and switch to default
            if name != defaultName:
                self.removeNonDefaultLst()
            else:
                if len(self.chooserDict) > 0:
                    # just choose the first model
                    self.removeDefaultLst()
                else:
                    self.removeLastLst()
            self.gui.setUnsavedChanges(True)


class subredditListViewAndChooser(listViewAndChooser):
    def __init__(self, gui):
        super().__init__(gui, gui.subredditListChooser, gui.rddtDataExtractor.subredditLists,
                         gui.rddtDataExtractor.defaultSubredditListName, Subreddit, "subreddit")
        self.rddtDataExtractor.currentSubredditListName = self.defaultLstName

    def chooseNewList(self, listIndex):
        listName = self.lstChooser.itemText(listIndex)
        print("Choosing new list: " + listName)
        self.rddtDataExtractor.currentSubredditListName = listName
        model = self.chooserDict.get(listName)
        self.setModel(model)

    def removeNonDefaultLst(self):
        self.rddtDataExtractor.currentSubredditListName = self.rddtDataExtractor.defaultSubredditListName
        name = self.rddtDataExtractor.currentSubredditListName
        index = self.lstChooser.findText(name)
        self.lstChooser.setCurrentIndex(index)
        self.chooseNewList(index)

    def removeDefaultLst(self):
        modelName = list(self.chooserDict)[0]
        self.rddtDataExtractor.currentSubredditListName = modelName
        self.rddtDataExtractor.defaultSubredditListName = modelName
        index = self.lstChooser.findText(modelName)
        self.lstChooser.setCurrentIndex(index)
        self.chooseNewList(index)

    def removeLastLst(self):
        print('deleting last list')
        self.rddtDataExtractor.currentSubredditListName = None
        self.rddtDataExtractor.defaultSubredditListName = None
        self.setModel(ListModel([], GenericListModelObj))

    def removeLst(self):
        name = self.lstChooser.currentText()
        if len(name) <= 0:
            return
        msgBox = confirmDialog("Are you sure you want to delete the " + self.objectName() + " list: " + name + "?")
        ret = msgBox.exec_()
        if ret == QMessageBox.Yes:
            if len(self.chooserDict) <= 0:
                QMessageBox.information(QMessageBox(), "Reddit Data Extractor",
                                        "There are no more lists left to delete.")
                return
            self.lstChooser.removeItem(self.lstChooser.currentIndex())
            del self.chooserDict[name]
            defaultName = self.rddtDataExtractor.defaultSubredditListName
            # if default is not being removed, just remove and switch to default
            if name != defaultName:
                self.removeNonDefaultLst()
            else:
                if len(self.chooserDict) > 0:
                    # just choose the first model
                    self.removeDefaultLst()
                else:
                    self.removeLastLst()
            self.gui.setUnsavedChanges(True)


class RddtDataExtractorGUI(QMainWindow, Ui_RddtDataExtractorMainWindow):
    def __init__(self, rddtDataExtractor, queue, recv):
        QMainWindow.__init__(self)

        # Set up the user interface from Designer.
        self.setupUi(self)

        self.rddtDataExtractor = rddtDataExtractor

        self.currentSelectedUserText = ""
        self.currentSelectedSubredditText = ""

        self.unsavedChanges = False

        self.log = True

        self.queue = queue
        self.recv = recv

        # Custom Set ups
        self.setup()

    def setup(self):
        self.init()

        self.directoryBox.setText(self.rddtDataExtractor.defaultPath)

        self.directorySelectBtn.clicked.connect(self.selectDirectory)
        self.addUserBtn.clicked.connect(self.userList.addToList)
        self.addSubredditBtn.clicked.connect(self.subredditList.addToList)

        self.deleteUserBtn.clicked.connect(self.userList.deleteFromList)
        self.deleteSubredditBtn.clicked.connect(self.subredditList.deleteFromList)

        self.actionSettings_2.triggered.connect(self.showSettings)
        self.actionExit.triggered.connect(self.close)
        self.actionSubreddit_List.triggered.connect(self.subredditList.makeNewList)
        self.actionUser_List.triggered.connect(self.userList.makeNewList)
        self.actionSave.triggered.connect(self.saveState)

        self.actionRemove_Subreddit_List.triggered.connect(self.subredditList.removeLst)
        self.actionRemove_User_List.triggered.connect(self.userList.removeLst)

        self.userListChooser.addAction(self.actionUser_List)
        self.subredditListChooser.addAction(self.actionSubreddit_List)
        self.userListChooser.addAction(self.actionRemove_User_List)
        self.subredditListChooser.addAction(self.actionRemove_Subreddit_List)

        self.userListChooser.activated.connect(self.userList.chooseNewList)
        self.subredditListChooser.activated.connect(self.subredditList.chooseNewList)

        self.userList.addAction(self.actionDownloaded_Reddit_User_Posts)
        self.userList.addAction(self.actionNew_User)
        self.userList.addAction(self.actionRemove_Selected_User)
        self.actionDownloaded_Reddit_User_Posts.triggered.connect(self.userList.viewDownloadedPosts)
        self.actionNew_User.triggered.connect(self.userList.addToList)
        self.actionRemove_Selected_User.triggered.connect(self.userList.deleteFromList)

        self.subredditList.addAction(self.actionDownloaded_Subreddit_Posts)
        self.subredditList.addAction(self.actionNew_Subreddit)
        self.subredditList.addAction(self.actionRemove_Selected_Subreddit)
        self.actionDownloaded_Subreddit_Posts.triggered.connect(self.subredditList.viewDownloadedPosts)
        self.actionNew_Subreddit.triggered.connect(self.subredditList.addToList)
        self.actionRemove_Selected_Subreddit.triggered.connect(self.subredditList.deleteFromList)

        self.downloadBtn.clicked.connect(self.beginDownload)

        self.userSubBtn.clicked.connect(
            lambda: self.rddtDataExtractor.changeDownloadType(DownloadType.USER_SUBREDDIT_CONSTRAINED))
        self.allUserBtn.clicked.connect(
            lambda: self.rddtDataExtractor.changeDownloadType(DownloadType.USER_SUBREDDIT_ALL))
        self.allSubBtn.clicked.connect(
            lambda: self.rddtDataExtractor.changeDownloadType(DownloadType.SUBREDDIT_CONTENT))

        self.actionAbout.triggered.connect(self.displayAbout)

    def initUserList(self):
        self.userList = userListViewAndChooser(self)
        self.gridLayout.addWidget(self.userList, 1, 0, 1, 1)

    def initSubredditList(self):
        self.subredditList = subredditListViewAndChooser(self)
        self.gridLayout.addWidget(self.subredditList, 1, 1, 1, 1)

    def init(self):
        self.initUserList()
        self.initSubredditList()
        if (self.rddtDataExtractor.downloadType == DownloadType.USER_SUBREDDIT_CONSTRAINED):
            self.userSubBtn.setChecked(True)
        elif (self.rddtDataExtractor.downloadType == DownloadType.USER_SUBREDDIT_ALL):
            self.allUserBtn.setChecked(True)
        elif (self.rddtDataExtractor.downloadType == DownloadType.SUBREDDIT_CONTENT):
            self.allSubBtn.setChecked(True)

    @pyqtSlot()
    def beginDownload(self):
        self.downloadBtn.setText("Downloading...")
        self.downloadBtn.setEnabled(False)
        self.logTextEdit.clear()
        if self.rddtDataExtractor.downloadType == DownloadType.USER_SUBREDDIT_CONSTRAINED:
            # need to validate both subreddits and redditors, start downloading user data once done
            self.getValidSubreddits()
            self.getValidRedditors(startDownload=True)
        elif self.rddtDataExtractor.downloadType == DownloadType.USER_SUBREDDIT_ALL:
            self.getValidRedditors(startDownload=True)
        elif self.rddtDataExtractor.downloadType == DownloadType.SUBREDDIT_CONTENT:
            self.getValidSubreddits(startDownload=True)

    @pyqtSlot(list)
    def downloadValid(self, validData):
        if self.rddtDataExtractor.downloadType == DownloadType.USER_SUBREDDIT_CONSTRAINED or self.rddtDataExtractor.downloadType == DownloadType.USER_SUBREDDIT_ALL:
            self.downloader = Downloader(self.rddtDataExtractor, validData, self.queue, ListType.USER)
        elif self.rddtDataExtractor.downloadType == DownloadType.SUBREDDIT_CONTENT:
            self.downloader = Downloader(self.rddtDataExtractor, validData, self.queue, ListType.SUBREDDIT)
        self.thread = QThread()
        self.downloader.moveToThread(self.thread)
        self.thread.started.connect(self.downloader.run)
        self.downloader.finished.connect(self.thread.quit)
        self.downloader.finished.connect(self.activateDownloadBtn)
        self.downloader.finished.connect(self.downloader.deleteLater)
        self.downloader.finished.connect(lambda: self.setUnsavedChanges(True))
        self.thread.finished.connect(self.thread.deleteLater)
        self.thread.start()

    @pyqtSlot(str)
    def append_text(self, text):
        self.logTextEdit.moveCursor(QTextCursor.End)
        self.logTextEdit.insertPlainText(text)

    def activateDownloadBtn(self):
        self.downloadBtn.setText("Download!")
        self.downloadBtn.setEnabled(True)
        self.rddtDataExtractor.currentlyDownloading = False

    def getValidRedditors(self, startDownload=False):
        model = self.userList.model()
        users = set(model.lst)  # create a new set so we don't change set size during iteration if we remove a user
        # These are class variables so that they don't get destroyed when we return from getValidRedditors()
        self.redditorValidatorThread = QThread()
        self.redditorValidator = Validator(self.rddtDataExtractor, self.queue, users, ListType.USER)
        self.redditorValidator.moveToThread(self.redditorValidatorThread)
        self.redditorValidatorThread.started.connect(self.redditorValidator.run)
        self.redditorValidator.invalid.connect(self.notifyInvalidRedditor)
        # When the validation finishes, start the downloading process on the validated users
        if startDownload:
            self.redditorValidator.finished.connect(self.downloadValid)
        self.redditorValidator.finished.connect(self.redditorValidatorThread.quit)
        self.redditorValidator.finished.connect(self.redditorValidator.deleteLater)
        self.redditorValidatorThread.finished.connect(self.redditorValidatorThread.deleteLater)
        self.redditorValidatorThread.start()

    @pyqtSlot(str)
    def notifyInvalidRedditor(self, userName):
        model = self.userList.model()
        msgBox = confirmDialog("The user " + userName + " does not exist. Remove from list?")
        ret = msgBox.exec_()
        if ret == QMessageBox.Yes:
            index = model.getIndexOfName(userName)
            if index != -1:
                model.removeRows(index, 1)

    def getValidSubreddits(self, startDownload=False):
        model = self.subredditList.model()
        subreddits = set(model.lst)
        self.subredditValidatorThread = QThread()
        self.subredditValidator = Validator(self.rddtDataExtractor, self.queue, subreddits, ListType.SUBREDDIT)
        self.subredditValidator.moveToThread(self.subredditValidatorThread)
        self.subredditValidatorThread.started.connect(self.subredditValidator.run)
        self.subredditValidator.invalid.connect(self.notifyInvalidSubreddit)
        if startDownload:
            self.subredditValidator.finished.connect(self.downloadValid)
        self.subredditValidator.finished.connect(self.subredditValidatorThread.quit)
        self.subredditValidator.finished.connect(self.subredditValidator.deleteLater)
        self.subredditValidatorThread.finished.connect(self.subredditValidatorThread.deleteLater)
        self.subredditValidatorThread.start()

    @pyqtSlot(str)
    def notifyInvalidSubreddit(self, subredditName):
        model = self.subredditList.model()
        msgBox = confirmDialog("The subreddit " + subredditName + " does not exist. Remove from list?")
        ret = msgBox.exec_()
        if ret == QMessageBox.Yes:
            index = model.getIndexOfName(subredditName)
            if index != -1:
                model.removeRows(index, 1)

    def selectDirectory(self):
        directory = QFileDialog.getExistingDirectory(QFileDialog())
        if len(directory) > 0 and os.path.exists(directory):
            self.rddtDataExtractor.defaultPath = directory
            self.directoryBox.setText(directory)
            self.setUnsavedChanges(True)

    def convertFilterTableToFilters(self, settings):
        filterTable = settings.filterTable
        postFilts = []
        commentFilts = []
        connector = None
        if filterTable.rowCount() > 0:
            connectorWidget = filterTable.cellWidget(0, settings.filtTableConnectCol)
            if connectorWidget is not None:
                connector = self.rddtDataExtractor.mapConnectorTextToOper(connectorWidget.currentText())
            else:
                connector = None  # We are just filtering by a single thing
            for row in range(filterTable.rowCount()):
                print("row: " + str(row))
                type = filterTable.cellWidget(row, settings.filtTableTypeCol).currentText()
                prop = filterTable.cellWidget(row, settings.filtTablePropCol).currentText()
                oper = self.rddtDataExtractor.mapFilterTextToOper(
                    filterTable.cellWidget(row, settings.filtTableOperCol).currentText())
                val = filterTable.cellWidget(row, settings.filtTableValCol).toPlainText()
                if val.lower() == "false":
                    val = False
                elif val.lower() == "true":
                    val = True
                elif isNumber(val):
                    val = float(val)
                filt = (prop, oper, val)
                if type == "Submission":
                    postFilts.append(filt)
                elif type == "Comment":
                    commentFilts.append(filt)
        print(postFilts, commentFilts, connector)
        return postFilts, commentFilts, connector

    def showSettings(self):
        settings = SettingsGUI(self.rddtDataExtractor)
        ret = settings.exec_()
        if ret == QDialog.Accepted:
            self.logPrint(
                "Saving settings:\n" + str(settings.currentUserListName) + "\n" + str(
                    settings.currentSubredditListName))
            self.rddtDataExtractor.defaultUserListName = settings.currentUserListName
            self.rddtDataExtractor.defaultSubredditListName = settings.currentSubredditListName

            self.rddtDataExtractor.avoidDuplicates = settings.avoidDuplicates
            self.rddtDataExtractor.getExternalContent = settings.getExternalContent
            self.rddtDataExtractor.getCommentExternalContent = settings.getCommentExternalContent
            self.rddtDataExtractor.getSelftextExternalContent = settings.getSelftextExternalContent
            self.rddtDataExtractor.getSubmissionContent = settings.getSubmissionContent

            self.rddtDataExtractor.subSort = settings.subSort
            self.rddtDataExtractor.subLimit = settings.subLimit
            self.rddtDataExtractor.filterExternalContent = settings.filterExternalContent
            self.rddtDataExtractor.filterSubmissionContent = settings.filterSubmissionContent
            if settings.filterExternalContent or settings.filterSubmissionContent:
                self.rddtDataExtractor.postFilts, self.rddtDataExtractor.commentFilts, self.rddtDataExtractor.connector = self.convertFilterTableToFilters(
                    settings)

            self.rddtDataExtractor.restrictDownloadsByCreationDate = settings.restrictDownloadsByCreationDate
            self.saveState()

    def displayAbout(self):
        msgBox = QMessageBox()
        msgBox.setTextFormat(Qt.RichText)
        msgBox.setWindowTitle("Reddit Data Extractor")
        msgBox.setText("""
            <p>This program uses the following open source software:<br>
            <a href="http://www.riverbankcomputing.co.uk/software/pyqt/intro">PyQt</a> under the GNU GPL v3 license
            </p>

            <p>This program makes use of a modified version of <a href="https://www.videolan.org/vlc/">VLC's</a> logo:<br>
            Copyright (c) 1996-2013 VideoLAN. This logo or a modified version may<br>
            be used or modified by anyone to refer to the VideoLAN project or any<br>
            product developed by the VideoLAN team, but does not indicate<br>
            endorsement by the project.
            </p>

            <p>This program makes use of a modified version of Microsoft Window's<br>
            .txt file icon. This is solely the property of Microsoft Windows<br>
            and I claim no ownership.
            </p>

            <p>This program is released under the GNU GPL v3 license<br>
            <a href="https://www.gnu.org/licenses/quick-guide-gplv3.html">GNU GPL v3 license page</a>
            </p>
        """)
        msgBox.exec()


    def setUnsavedChanges(self, unsaved):
        self.unsavedChanges = unsaved
        if self.unsavedChanges:
            self.setWindowTitle("Reddit Data Extractor *")
        else:
            self.setWindowTitle("Reddit Data Extractor")

    def checkSaveState(self):
        close = False
        if self.unsavedChanges:
            msgBox = QMessageBox()
            msgBox.setText("A list or setting has been changed.")
            msgBox.setInformativeText("Do you want to save your changes?")
            msgBox.setStandardButtons(QMessageBox.Save | QMessageBox.Discard | QMessageBox.Cancel)
            msgBox.setDefaultButton(QMessageBox.Save)
            ret = msgBox.exec_()
            if ret == QMessageBox.Save:
                self.saveState()
                close = True
            elif ret == QMessageBox.Discard:
                close = True
            elif ret == QMessageBox.Cancel:
                close = False
            else:
                close = False
        else:
            close = True
        return close

    def closeEvent(self, event):
        self.logPrint("Attempting to close program.")
        close = self.checkSaveState()
        if close:
            self.recv.stop()
            self.logPrint("Closing program.")
            event.accept()
        else:
            self.logPrint("Ignoring close attempt.")
            event.ignore()

    def logPrint(self, s):
        if self.log:
            print(s)

    def saveState(self):
        successful = self.rddtDataExtractor.saveState()
        self.setUnsavedChanges(not successful)