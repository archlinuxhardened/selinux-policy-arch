#!/usr/bin/env python3
# Copyright (C) 2004 Tresys Technology, LLC
# see file 'COPYING' for use and warranty information
#
# genhomedircon - this script is used to generate file context
# configuration entries for user home directories based on their
# default roles and is run when building the policy. Specifically, we
# replace HOME_ROOT, HOME_DIR, and ROLE macros in .fc files with
# generic and user-specific values.
#
# Based off original script by Dan Walsh, <dwalsh@redhat.com>
#
# ASSUMPTIONS:
#
# The file CONTEXTDIR/files/homedir_template exists.  This file is used to
# set up the home directory context for each real user.
#
# If a user has more than one role in CONTEXTDIR/local.users, genhomedircon uses
#  the first role in the list.
#
# If a user is not listed in CONTEXTDIR/local.users, he will default to user_u, role user
#
# "Real" users (as opposed to system users) are those whose UID is greater than
#  or equal STARTING_UID (usually 500) and whose login is not a member of
#  EXCLUDE_LOGINS.  Users who are explicitly defined in CONTEXTDIR/local.users
#  are always "real" (including root, in the default configuration).
#
#
# Old ASSUMPTIONS:
#
# If a user has more than one role in FILECONTEXTDIR/users, genhomedircon uses
#  the first role in the list.
#
# If a user is not listed in FILECONTEXTDIR/users, genhomedircon assumes that
#  the user's home dir will be found in one of the HOME_ROOTs.
#
# "Real" users (as opposed to system users) are those whose UID is greater than
#  or equal STARTING_UID (usually 500) and whose login is not a member of
#  EXCLUDE_LOGINS.  Users who are explicitly defined in FILECONTEXTDIR/users
#  are always "real" (including root, in the default configuration).
#

import sys, os, pwd, getopt, re

EXCLUDE_LOGINS=["/sbin/nologin", "/bin/false"]

# Python 2/3 wrapper
def getstatusoutput_wrapper(cmd):
    if sys.version_info.major == 2:
        import commands
        return commands.getstatusoutput(cmd)
    elif sys.version_info.major == 3:
        import subprocess
        return subprocess.getstatusoutput(cmd)
    else:
        print("Unsupported Python major version: " + sys.version_info.major)
        exit(1)


def getStartingUID():
	starting_uid = 99999
	rc=getstatusoutput_wrapper("grep -h '^UID_MIN' /etc/login.defs")
	if rc[0] == 0:
		uid_min = re.sub("^UID_MIN[^0-9]*", "", rc[1])
		#stip any comment from the end of the line
		uid_min = uid_min.split("#")[0]
		uid_min = uid_min.strip()
		if int(uid_min) < starting_uid:
			starting_uid = int(uid_min)
	rc=getstatusoutput_wrapper("grep -h '^LU_UIDNUMBER' /etc/libuser.conf")
	if rc[0] == 0:
		lu_uidnumber = re.sub("^LU_UIDNUMBER[^0-9]*", "", rc[1])
		#stip any comment from the end of the line
		lu_uidnumber = re.sub("[ \t].*", "", lu_uidnumber)
		lu_uidnumber = lu_uidnumber.split("#")[0]
		lu_uidnumber = lu_uidnumber.strip()
		if int(lu_uidnumber) < starting_uid:
			starting_uid = int(lu_uidnumber)
	if starting_uid == 99999:
		starting_uid = 500
	return starting_uid

#############################################################################
#
# This section is just for backwards compatability
#
#############################################################################
def getPrefixes():
	ulist = pwd.getpwall()
	STARTING_UID=getStartingUID()
	prefixes = {}
	for u in ulist:
		if u[2] >= STARTING_UID and \
				not u[6] in EXCLUDE_LOGINS and \
				u[5] != "/" and \
				u[5].count("/") > 1:
			prefix = u[5][:u[5].rfind("/")]
			if not prefix in prefixes:
				prefixes[prefix] = ""
	return prefixes

def getUsers(filecontextdir):
	rc = getstatusoutput_wrapper("grep ^user %s/users" % filecontextdir)
	udict = {}
	if rc[0] == 0:
		ulist = rc[1].strip().split("\n")
		for u in ulist:
			user = u.split()
			try:
				if user[1] == "user_u" or user[1] == "system_u":
					continue
				# !!! chooses first role in the list to use in the file context !!!
				role = user[3]
				if role == "{":
					role = user[4]
				role = role.split("_r")[0]
				home = pwd.getpwnam(user[1])[5]
				if home == "/":
					continue
				prefs = {}
				prefs["role"] = role
				prefs["home"] = home
				udict[user[1]] = prefs
			except KeyError:
				sys.stderr.write("The user \"%s\" is not present in the passwd file, skipping...\n" % user[1])
	return udict

def update(filecontext, user, prefs):
	rc=getstatusoutput_wrapper("grep -h '^HOME_DIR' %s | grep -v vmware | sed -e 's|HOME_DIR|%s|' -e 's/ROLE/%s/' -e 's/system_u/%s/'" % (filecontext, prefs["home"], prefs["role"], user))
	if rc[0] == 0:
		print(rc[1])
	else:
		errorExit("grep/sed error " + rc[1])
	return rc

def oldgenhomedircon(filecontextdir, filecontext):
        sys.stderr.flush()

        if os.path.isdir(filecontextdir) == 0:
                sys.stderr.write("New usage is the following\n")
                usage()
        #We are going to define home directory used by libuser and show-utils as a home directory root
        prefixes = {}
        rc=getstatusoutput_wrapper("grep -h '^HOME' /etc/default/useradd")
        if rc[0] == 0:
                homedir = rc[1].split("=")[1]
                homedir = homedir.split("#")[0]
                homedir = homedir.strip()
                if not homedir in prefixes:
                        prefixes[homedir] = ""
        else:
                #rc[0] == 256 means the file was there, we read it, but the grep didn't match
                if rc[0] != 256:
                        sys.stderr.write("%s\n" % rc[1])
                        sys.stderr.write("You do not have access to /etc/default/useradd HOME=\n")
                        sys.stderr.flush()


        rc=getstatusoutput_wrapper("grep -h '^LU_HOMEDIRECTORY' /etc/libuser.conf")
        if rc[0] == 0:
                homedir = rc[1].split("=")[1]
                homedir = homedir.split("#")[0]
                homedir = homedir.strip()
                homedir = re.sub(r"[^/a-zA-Z0-9].*$", "", homedir)
                if not homedir in prefixes:
                        prefixes[homedir] = ""

        #the idea is that we need to find all of the home_root_t directories we do this by just accepting
        #any default home directory defined by either /etc/libuser.conf or /etc/default/useradd
        #we then get the potential home directory roots from /etc/passwd or nis or wherever and look at
        #the defined homedir for all users with UID > STARTING_UID.  This list of possible root homedirs
        #is then checked to see if it has an explicite context defined in the file_contexts.  Explicit
        #is any regex that would match it which does not end with .*$ or .+$ since those are general
        #recursive matches.  We then take any regex which ends with [pattern](/.*)?$ and just check against
        #[pattern]
        potential_prefixes = getPrefixes()
        prefix_regex = {}
        #this works by grepping the file_contexts for
        # 1. ^/ makes sure this is not a comment
        # 2. prints only the regex in the first column first cut on \t then on space
        rc=getstatusoutput_wrapper("grep \"^/\" %s | cut -f 1 | cut -f 1 -d \" \" " %  (sys.argv[2]) )
        if rc[0] == 0:
                prefix_regex = rc[1].split("\n")
        else:
                sys.stderr.write("%s\n" % rc[1])
                sys.stderr.write("You do not have access to grep/cut/the file contexts\n")
                sys.stderr.flush()
        for potential in potential_prefixes.keys():
                addme = 1
                for regex in prefix_regex:
                        #match a trailing (/*)? which is actually a bug in rpc_pipefs
                        regex = re.sub(r"\(/\*\)\?$", "", regex)
                        #match a trailing .+
                        regex = re.sub(r"\.+$", "", regex)
                        #match a trailing .*
                        regex = re.sub(r"\.\*$", "", regex)
                        #strip a (/.*)? which matches anything trailing to a /*$ which matches trailing /'s
                        regex = re.sub(r"\(\/\.\*\)\?", "", regex)
                        regex = regex + "/*$"
                        if re.search(regex, potential, 0):
                                addme = 0
                if addme == 1:
                        if not potential in prefixes:
                                prefixes[potential] = ""


        if prefixes.__eq__({}):
                sys.stderr.write("LU_HOMEDIRECTORY not set in /etc/libuser.conf\n")
                sys.stderr.write("HOME= not set in /etc/default/useradd\n")
                sys.stderr.write("And no users with a reasonable homedir found in passwd/nis/ldap/etc...\n")
                sys.stderr.write("Assuming /home is the root of home directories\n")
                sys.stderr.flush()
                prefixes["/home"] = ""

        # There may be a more elegant sed script to expand a macro to multiple lines, but this works
        sed_root = "h; s|^HOME_ROOT|%s|" % (prefixes.keys() + "|; p; g; s|^HOME_ROOT|")
        sed_dir = "h; s|^HOME_DIR|%s/[^/]+|; s|ROLE_|user_|" % (prefixes.keys() + "/[^/]+|; s|ROLE_|user_|; p; g; s|^HOME_DIR|")

        # Fill in HOME_ROOT, HOME_DIR, and ROLE for users not explicitly defined in /etc/security/selinux/src/policy/users
        rc=getstatusoutput_wrapper("sed -e \"/^HOME_ROOT/{%s}\" -e \"/^HOME_DIR/{%s}\" %s" % (sed_root, sed_dir, filecontext))
        if rc[0] == 0:
                print(rc[1])
        else:
                errorExit("sed error " + rc[1])

        users = getUsers(filecontextdir)
        print("\n#\n# User-specific file contexts\n#\n")

        # Fill in HOME and ROLE for users that are defined
        for u in users.keys():
                update(filecontext, u, users[u])

#############################################################################
#
# End of backwards compatability section
#
#############################################################################

def getDefaultHomeDir():
	ret = []
	rc=getstatusoutput_wrapper("grep -h '^HOME' /etc/default/useradd")
	if rc[0] == 0:
		homedir = rc[1].split("=")[1]
		homedir = homedir.split("#")[0]
		homedir = homedir.strip()
		if not homedir in ret:
			ret.append(homedir)
	else:
		#rc[0] == 256 means the file was there, we read it, but the grep didn't match
		if rc[0] != 256:
			sys.stderr.write("%s\n" % rc[1])
			sys.stderr.write("You do not have access to /etc/default/useradd HOME=\n")
			sys.stderr.flush()
	rc=getstatusoutput_wrapper("grep -h '^LU_HOMEDIRECTORY' /etc/libuser.conf")
	if rc[0] == 0:
		homedir = rc[1].split("=")[1]
		homedir = homedir.split("#")[0]
		homedir = homedir.strip()
		if not homedir in ret:
			ret.append(homedir)
	else:
		#rc[0] == 256 means the file was there, we read it, but the grep didn't match
		if rc[0] != 256:
			sys.stderr.write("%s\n" % rc[1])
			sys.stderr.write("You do not have access to /etc/libuser.conf LU_HOMEDIRECTORY=\n")
			sys.stderr.flush()
	if ret == []:
		ret.append("/home")
	return ret

def getSELinuxType(directory):
	rc=getstatusoutput_wrapper("grep ^SELINUXTYPE= %s/config" % directory)
	if rc[0]==0:
		return rc[1].split("=")[-1].strip()
	return "targeted"

def usage(error = ""):
	if error != "":
		sys.stderr.write("%s\n" % error)
	sys.stderr.write("Usage: %s [ -d selinuxdir ] [-n | --nopasswd] [-t selinuxtype ]\n" % sys.argv[0])
	sys.stderr.flush()
	sys.exit(1)

def warning(warning = ""):
	sys.stderr.write("%s\n" % warning)
	sys.stderr.flush()

def errorExit(error):
	sys.stderr.write("%s exiting for: " % sys.argv[0])
	sys.stderr.write("%s\n" % error)
	sys.stderr.flush()
	sys.exit(1)

class selinuxConfig:
	def __init__(self, selinuxdir="/etc/selinux", setype="targeted", usepwd=1):
		self.setype=setype
		self.selinuxdir=selinuxdir +"/"
		self.contextdir="/contexts"
		self.filecontextdir=self.contextdir+"/files"
		self.usepwd=usepwd

	def getFileContextDir(self):
		return self.selinuxdir+self.setype+self.filecontextdir

	def getFileContextFile(self):
		return self.getFileContextDir()+"/file_contexts"

	def getContextDir(self):
		return self.selinuxdir+self.setype+self.contextdir

	def getHomeDirTemplate(self):
		return self.getFileContextDir()+"/homedir_template"

	def getHomeRootContext(self, homedir):
		rc=getstatusoutput_wrapper("grep HOME_ROOT  %s | sed -e \"s|^HOME_ROOT|%s|\"" % ( self.getHomeDirTemplate(), homedir))
		if rc[0] == 0:
			return rc[1]+"\n"
		else:
			errorExit("sed error " + rc[1])

	def getUsersFile(self):
		return self.selinuxdir+self.setype+"/users/local.users"

	def getSystemUsersFile(self):
		return self.selinuxdir+self.setype+"/users/system.users"

	def heading(self):
		ret = "\n#\n#\n# User-specific file contexts, generated via %s\n" % sys.argv[0]
		ret += "# edit %s to change file_context\n#\n#\n" % self.getUsersFile()
		return ret

	def getUsers(self):
		users=""
		rc = getstatusoutput_wrapper('grep "^user" %s' % self.getSystemUsersFile())
		if rc[0] == 0:
			users+=rc[1]+"\n"
		rc = getstatusoutput_wrapper("grep ^user %s" % self.getUsersFile())
		if rc[0] == 0:
			users+=rc[1]
		udict = {}
		prefs = {}
		if users != "":
			ulist = users.split("\n")
			for u in ulist:
				user = u.split()
				try:
					if len(user)==0 or user[1] == "user_u" or user[1] == "system_u":
						continue
					# !!! chooses first role in the list to use in the file context !!!
					role = user[3]
					if role == "{":
						role = user[4]
					role = role.split("_r")[0]
					home = pwd.getpwnam(user[1])[5]
					if home == "/":
						continue
					prefs = {}
					prefs["role"] = role
					prefs["home"] = home
					udict[user[1]] = prefs
				except KeyError:
					sys.stderr.write("The user \"%s\" is not present in the passwd file, skipping...\n" % user[1])
		return udict

	def getHomeDirContext(self, user, home, role):
		ret="\n\n#\n# Context for user %s\n#\n\n" % user
		rc=getstatusoutput_wrapper("grep '^HOME_DIR' %s | sed -e 's|HOME_DIR|%s|' -e 's/ROLE/%s/' -e 's/system_u/%s/'" % (self.getHomeDirTemplate(), home, role, user))
		return ret + rc[1] + "\n"

	def genHomeDirContext(self):
		users = self.getUsers()
		ret=""
		# Fill in HOME and ROLE for users that are defined
		for u in users.keys():
			ret += self.getHomeDirContext (u, users[u]["home"], users[u]["role"])
		return ret+"\n"

	def checkExists(self, home):
		if getstatusoutput_wrapper("grep -E '^%s[^[:alnum:]_-]' %s" % (home, self.getFileContextFile()))[0] == 0:
			return 0
		#this works by grepping the file_contexts for
		# 1. ^/ makes sure this is not a comment
		# 2. prints only the regex in the first column first cut on \t then on space
		rc=getstatusoutput_wrapper("grep \"^/\" %s | cut -f 1 | cut -f 1 -d \" \" " %  self.getFileContextFile() )
		if rc[0] == 0:
			prefix_regex = rc[1].split("\n")
		else:
			sys.stderr.write("%s\n" % rc[1])
			sys.stderr.write("You do not have access to grep/cut/the file contexts\n")
			sys.stderr.flush()
		exists=1
		for regex in prefix_regex:
			#match a trailing (/*)? which is actually a bug in rpc_pipefs
			regex = re.sub(r"\(/\*\)\?$", "", regex)
			#match a trailing .+
			regex = re.sub(r"\.+$", "", regex)
			#match a trailing .*
			regex = re.sub(r"\.\*$", "", regex)
			#strip a (/.*)? which matches anything trailing to a /*$ which matches trailing /'s
			regex = re.sub(r"\(\/\.\*\)\?", "", regex)
			regex = regex + "/*$"
			if re.search(regex, home, 0):
				exists = 0
				break
		if exists == 1:
			return 1
		else:
			return 0


	def getHomeDirs(self):
		homedirs = []
		homedirs = homedirs + getDefaultHomeDir()
		starting_uid=getStartingUID()
		if self.usepwd==0:
			return homedirs
		ulist = pwd.getpwall()
		for u in ulist:
			if u[2] >= starting_uid and \
					not u[6] in EXCLUDE_LOGINS and \
					u[5] != "/" and \
					u[5].count("/") > 1:
				homedir = u[5][:u[5].rfind("/")]
				if not homedir in homedirs:
					if self.checkExists(homedir)==0:
						warning("%s is already defined in %s,\n%s will not create a new context." % (homedir, self.getFileContextFile(), sys.argv[0]))
					else:
						homedirs.append(homedir)

		homedirs.sort()
		return homedirs

	def genoutput(self):
		ret= self.heading()
		for h in self.getHomeDirs():
			ret += self.getHomeDirContext ("user_u" , h+'/[^/]*', "user")
			ret += self.getHomeRootContext(h)
		ret += self.genHomeDirContext()
		return ret

	def printout(self):
		print(self.genoutput())

	def write(self):
		try:
			fd = open(self.getFileContextDir()+"/file_contexts.homedirs", "w")
			fd.write(self.genoutput())
			fd.close()
		except IOError as error:
			sys.stderr.write("%s: %s\n" % ( sys.argv[0], error ))



#
# This script will generate home dir file context
# based off the homedir_template file, entries in the password file, and
#
try:
	usepwd=1
	directory="/etc/selinux"
	setype=None
	gopts, cmds = getopt.getopt(sys.argv[1:], 'nd:t:', ['help',
						'type=',
						'nopasswd',
						'dir='])
	for o,a in gopts:
		if o == '--type' or o == "-t":
			setype=a
		if o == '--nopasswd'  or o == "-n":
			usepwd=0
		if o == '--dir'  or o == "-d":
			directory=a
		if o == '--help':
			usage()


	if setype is None:
		setype=getSELinuxType(directory)

	if len(cmds) == 2:
		oldgenhomedircon(cmds[0], cmds[1])
		sys.exit(0)

	if len(cmds) != 0:
		usage()
	selconf=selinuxConfig(directory, setype, usepwd)
	selconf.write()

except Exception as error:
	errorExit(error)
