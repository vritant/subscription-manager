SHELL := /bin/bash
PREFIX ?=
SYSCONF ?= etc
PYTHON ?= python

INSTALL_DIR = usr/share
INSTALL_MODULE = rhsm
PKGNAME = subscription_manager
ANACONDA_ADDON_NAME = com_redhat_subscription_manager

# where most of our python modules live. Note this is not on
# the default python system path. If you are importing modules from here, and
# you can't commit to this repo, you should feel bad and stop doing that.
PYTHON_INST_DIR = $(PREFIX)/$(INSTALL_DIR)/$(INSTALL_MODULE)/$(PKGNAME)

OS = $(shell lsb_release -i | awk '{ print $$3 }' | awk -F. '{ print $$1}')
OS_VERSION = $(shell lsb_release -r | awk '{ print $$2 }' | awk -F. '{ print $$1}')
OS_DIST ?= $(shell rpm --eval='%dist')
BIN_DIR := bin/
BIN_FILES := $(BIN_DIR)/subscription-manager $(BIN_DIR)/subscription-manager-gui \
			 $(BIN_DIR)/rhn-migrate-classic-to-rhsm \
			 $(BIN_DIR)/rct \
			 $(BIN_DIR)/rhsm-debug

# Where various bits of code live in the git repo
BASE_SRC_DIR := src
SRC_DIR := $(BASE_SRC_DIR)/subscription_manager
RCT_SRC_DIR := $(BASE_SRC_DIR)/rct
RD_SRC_DIR := $(BASE_SRC_DIR)/rhsm_debug
RHSM_ICON_SRC_DIR := $(BASE_SRC_DIR)/rhsm_icon
DAEMONS_SRC_DIR := $(BASE_SRC_DIR)/daemons
EXAMPLE_PLUGINS_SRC_DIR := example-plugins/
CONTENT_PLUGINS_SRC_DIR := $(BASE_SRC_DIR)/content_plugins/
ANACONDA_ADDON_SRC_DIR := $(BASE_SRC_DIR)/initial-setup
ANACONDA_ADDON_MODULE_SRC_DIR := $(ANACONDA_ADDON_SRC_DIR)/$(ANACONDA_ADDON_NAME)

# dirs we install to
SUBMAN_INST_DIR := $(PREFIX)/$(INSTALL_DIR)/$(INSTALL_MODULE)/$(PKGNAME)
SYSTEMD_INST_DIR := $(PREFIX)/usr/lib/systemd/system
RHSM_PLUGIN_DIR := $(PREFIX)/usr/share/rhsm-plugins/
RHSM_PLUGIN_CONF_DIR := $(PREFIX)/etc/rhsm/pluginconf.d/
ANACONDA_ADDON_INST_DIR := $(PREFIX)/usr/share/anaconda/addons
INITIAL_SETUP_INST_DIR := $(ANACONDA_ADDON_INST_DIR)/$(ANACONDA_ADDON_NAME)
RCT_INST_DIR := $(PREFIX)/$(INSTALL_DIR)/$(INSTALL_MODULE)/rct
RD_INST_DIR := $(PREFIX)/$(INSTALL_DIR)/$(INSTALL_MODULE)/rhsm_debug
RHSM_LOCALE_DIR := $(PREFIX)/$(INSTALL_DIR)/locale

# ui builder data files
GLADE_INST_DIR := $(SUBMAN_INST_DIR)/gui/data/glade
UI_INST_DIR := $(SUBMAN_INST_DIR)/gui/data/ui

# If we skip install ostree plugin, unset by default
# override from spec file for rhel6
INSTALL_OSTREE_PLUGIN ?= true

# Default differences between el6 and el7
ifeq ($(OS_DIST),.el6)
   GTK_VERSION?=2
   FIRSTBOOT_MODULES_DIR?=$(PREFIX)/usr/share/rhn/up2date_client/firstboot
   INSTALL_FIRSTBOOT?=true
   INSTALL_INITIAL_SETUP?=false
else
   GTK_VERSION?=3
   FIRSTBOOT_MODULES_DIR?=$(PREFIX)/usr/share/firstboot/modules
   INSTALL_FIRSTBOOT?=true
   INSTALL_INITIAL_SETUP?=true
endif


YUM_PLUGINS_SRC_DIR := $(BASE_SRC_DIR)/plugins
ALL_SRC_DIRS := $(SRC_DIR) $(RCT_SRC_DIR) $(RD_SRC_DIR) $(DAEMONS_SRC_DIR) $(CONTENT_PLUGINS_SRC_DIR) $(EXAMPLE_PLUGINS_SRC_DIR) $(YUM_PLUGINS_SRC_DIR)

# sets a version that is more or less latest tag plus commit sha
VERSION ?= $(shell git describe | awk ' { sub(/subscription-manager-/,"")};1' )

# inherit from env if set so rpm can override
CFLAGS ?= -g -Wall
LDFLAGS ?=


%.pyc: %.py
	python -c "import py_compile; py_compile.compile('$<')"

build: set-versions rhsmcertd rhsm-icon

# we never "remake" this makefile, so add a target so
# we stop searching for implicit rules on how to remake it
Makefile: ;

clean: clean-versions
	rm -f *.pyc *.pyo *~ *.bak *.tar.gz
	rm -f bin/rhsmcertd
	rm -f bin/rhsm-icon
	python setup.py clean

bin:
	mkdir bin

RHSMCERTD_FLAGS = `pkg-config --cflags --libs glib-2.0`

ICON_FLAGS=`pkg-config --cflags --libs "gtk+-$(GTK_VERSION).0 libnotify gconf-2.0 dbus-glib-1"`

PYFILES := `find $(ALL_SRC_DIRS) -name "*.py"`
EXAMPLE_PLUGINS_PYFILES := `find "$(EXAMPLE_PLUGINS_SRC_DIR)/*.py"`
# Ignore certdata.py from style checks as tabs and trailing
# whitespace are required for testing.
TESTFILES=`find  test/ \( ! -name certdata.py ! -name manifestdata.py \) -name "*.py"`
STYLEFILES=$(PYFILES) $(BIN_FILES) $(TESTFILES)
GLADEFILES=`find src/subscription_manager/gui/data/glade -name "*.glade"`
UIFILES=`find src/subscription_manager/gui/data/ui -name "*.ui"`

rhsmcertd: $(DAEMONS_SRC_DIR)/rhsmcertd.c bin
	$(CC) $(CFLAGS) $(LDFLAGS) $(RHSMCERTD_FLAGS) $(DAEMONS_SRC_DIR)/rhsmcertd.c -o bin/rhsmcertd

check-syntax:
	$(CC) $(CFLAGS) $(LDFLAGS) $(ICON_FLAGS) -o nul -S $(CHK_SOURCES)

rhsm-icon: $(RHSM_ICON_SRC_DIR)/rhsm_icon.c bin
	$(CC) $(CFLAGS) $(LDFLAGS) $(ICON_FLAGS) -o bin/rhsm-icon $(RHSM_ICON_SRC_DIR)/rhsm_icon.c

dbus-service-install:
	install -d $(PREFIX)/etc/dbus-1/system.d
	install -d $(PREFIX)/$(INSTALL_DIR)/dbus-1/system-services
	install -d $(PREFIX)/usr/libexec
	install -d $(PREFIX)/etc/bash_completion.d
	install -m 644 etc-conf/com.redhat.SubscriptionManager.conf \
		$(PREFIX)/etc/dbus-1/system.d
	install -m 644 etc-conf/com.redhat.SubscriptionManager.service \
		$(PREFIX)/$(INSTALL_DIR)/dbus-1/system-services
	install -m 744 $(DAEMONS_SRC_DIR)/rhsm_d.py \
		$(PREFIX)/usr/libexec/rhsmd

install-conf:
	install etc-conf/rhsm.conf $(PREFIX)/etc/rhsm/
	install -T etc-conf/logrotate.conf $(PREFIX)/etc/logrotate.d/subscription-manager
	install -T etc-conf/logging.conf $(PREFIX)/etc/rhsm/logging.conf
	install etc-conf/plugin/*.conf $(PREFIX)/etc/yum/pluginconf.d/
	install -m 644 etc-conf/subscription-manager.completion.sh $(PREFIX)/etc/bash_completion.d/subscription-manager
	install -m 644 etc-conf/rct.completion.sh $(PREFIX)/etc/bash_completion.d/rct
	install -m 644 etc-conf/rhsm-debug.completion.sh $(PREFIX)/etc/bash_completion.d/rhsm-debug
	install -m 644 etc-conf/rhn-migrate-classic-to-rhsm.completion.sh $(PREFIX)/etc/bash_completion.d/rhn-migrate-classic-to-rhsm
	install -m 644 etc-conf/rhsm-icon.completion.sh $(PREFIX)/etc/bash_completion.d/rhsm-icon
	install -m 644 etc-conf/rhsmcertd.completion.sh $(PREFIX)/etc/bash_completion.d/rhsmcertd
	install -m 644 etc-conf/subscription-manager-gui.appdata.xml $(PREFIX)/$(INSTALL_DIR)/appdata/subscription-manager-gui.appdata.xml

install-help-files:
	install -d $(PREFIX)/$(INSTALL_DIR)/gnome/help/subscription-manager
	install -d $(PREFIX)/$(INSTALL_DIR)/gnome/help/subscription-manager/C
	install -d \
		$(PREFIX)/$(INSTALL_DIR)/gnome/help/subscription-manager/C/figures
	install -d $(PREFIX)/$(INSTALL_DIR)/omf/subscription-manager
	install docs/subscription-manager.xml \
		$(PREFIX)/$(INSTALL_DIR)/gnome/help/subscription-manager/C
	install docs/legal.xml \
		$(PREFIX)/$(INSTALL_DIR)/gnome/help/subscription-manager/C
	install docs/figures/*.png \
		$(PREFIX)/$(INSTALL_DIR)/gnome/help/subscription-manager/C/figures
	install docs/subscription-manager-C.omf \
		$(PREFIX)/$(INSTALL_DIR)/omf/subscription-manager

install-content-plugin-ostree:
	if [ "$(INSTALL_OSTREE_PLUGIN)" = "true" ] ; then \
		install -m 644 $(CONTENT_PLUGINS_SRC_DIR)/ostree_content.py $(RHSM_PLUGIN_DIR) ; \
	fi;

install-content-plugins-conf-ostree:
	if [ "$(INSTALL_OSTREE_PLUGIN)" = "true" ] ; then \
		install -m 644 -p \
		$(CONTENT_PLUGINS_SRC_DIR)/ostree_content.OstreeContentPlugin.conf \
		$(RHSM_PLUGIN_CONF_DIR) ; \
	fi;

install-content-plugin-container:
	install -m 644 $(CONTENT_PLUGINS_SRC_DIR)/container_content.py $(RHSM_PLUGIN_DIR)

install-content-plugins-conf-container:
	install -m 644 -p \
		$(CONTENT_PLUGINS_SRC_DIR)/container_content.ContainerContentPlugin.conf \
		$(RHSM_PLUGIN_CONF_DIR)

install-content-plugins-dir:
	install -d $(RHSM_PLUGIN_DIR)

install-content-plugins-conf-dir:
	install -d $(RHSM_PLUGIN_CONF_DIR)

install-content-plugins-ca:
	install -d $(PREFIX)/etc/rhsm/ca
	install -m 644 -p etc-conf/redhat-entitlement-authority.pem $(PREFIX)/etc/rhsm/ca/redhat-entitlement-authority.pem

install-content-plugins-conf: install-content-plugins-conf-dir install-content-plugins-conf-ostree install-content-plugins-conf-container install-content-plugins-ca

install-content-plugins: install-content-plugins-dir install-content-plugin-ostree install-content-plugin-container


install-plugins-conf-dir:
	install -d $(RHSM_PLUGIN_CONF_DIR)

install-plugins-conf: install-plugins-conf-dir install-content-plugins-conf

install-plugins-dir:
	install -d $(RHSM_PLUGIN_DIR)

install-plugins: install-plugins-dir install-content-plugins

.PHONY: install-ga-dir
install-ga-dir:
	install -d $(PYTHON_INST_DIR)/ga_impls

# Install our gtk2/gtk3 compat modules
# just the gtk3 stuff
.PHONY: install-ga-gtk3
install-ga-gtk3: install-ga-dir
	install -m 644 -p $(SRC_DIR)/ga_impls/__init__.py* $(PYTHON_INST_DIR)/ga_impls
	install -m 644 -p $(SRC_DIR)/ga_impls/ga_gtk3.py* $(PYTHON_INST_DIR)/ga_impls

.PHONY: install-ga-gtk2
install-ga-gtk2: install-ga-dir
	install -d $(PYTHON_INST_DIR)/ga_impls/ga_gtk2
	install -m 644 -p $(SRC_DIR)/ga_impls/__init__.py* $(PYTHON_INST_DIR)/ga_impls
	install -m 644 -p $(SRC_DIR)/ga_impls/ga_gtk2/*.py $(PYTHON_INST_DIR)/ga_impls/ga_gtk2

.PHONY: install-ga
ifeq ($(GTK_VERSION),2)
 install-ga: install-ga-gtk2
else
 install-ga: install-ga-gtk3
endif

.PHONY: install-example-plugins
install-example-plugins: install-example-plugins-files install-example-plugins-conf

install-example-plugins-files:
	install -d $(RHSM_PLUGIN_DIR)
	install -m 644 -p $(EXAMPLE_PLUGINS_SRC_DIR)/*.py $(RHSM_PLUGIN_DIR)

install-example-plugins-conf:
	install -d $(RHSM_PLUGIN_CONF_DIR)
	install -m 644 -p $(EXAMPLE_PLUGINS_SRC_DIR)/*.conf $(RHSM_PLUGIN_CONF_DIR)

# initial-setup, as in the 'initial-setup' rpm that runs at first boot.
.PHONY: install-initial-setup-real
install-initial-setup-real:
	echo "installing initial-setup" ; \
	install -m 644 $(CONTENT_PLUGINS_SRC_DIR)/ostree_content.py $(RHSM_PLUGIN_DIR)
	install -d $(ANACONDA_ADDON_INST_DIR)
	install -d $(INITIAL_SETUP_INST_DIR)
	install -d $(INITIAL_SETUP_INST_DIR)/gui
	install -d $(INITIAL_SETUP_INST_DIR)/gui/spokes
	install -d $(INITIAL_SETUP_INST_DIR)/categories
	install -d $(INITIAL_SETUP_INST_DIR)/ks
	install -m 644 -p $(ANACONDA_ADDON_MODULE_SRC_DIR)/*.py $(INITIAL_SETUP_INST_DIR)/
	install -m 644 -p $(ANACONDA_ADDON_MODULE_SRC_DIR)/gui/*.py $(INITIAL_SETUP_INST_DIR)/gui/
	install -m 644 -p $(ANACONDA_ADDON_MODULE_SRC_DIR)/categories/*.py $(INITIAL_SETUP_INST_DIR)/categories/
	install -m 644 -p $(ANACONDA_ADDON_MODULE_SRC_DIR)/gui/spokes/*.py $(INITIAL_SETUP_INST_DIR)/gui/spokes/
	install -m 644 -p $(ANACONDA_ADDON_MODULE_SRC_DIR)/gui/spokes/*.ui $(INITIAL_SETUP_INST_DIR)/gui/spokes/
	install -m 644 -p $(ANACONDA_ADDON_MODULE_SRC_DIR)/ks/*.py $(INITIAL_SETUP_INST_DIR)/ks/

.PHONY: install-firstboot-real
install-firstboot-real:
	echo "Installing firstboot to $(FIRSTBOOT_MODULES_DIR)"; \
	install -d $(FIRSTBOOT_MODULES_DIR); \
	install -m644 $(SRC_DIR)/gui/firstboot/*.py* $(FIRSTBOOT_MODULES_DIR)/;\


.PHONY: install-firstboot
ifeq ($(INSTALL_FIRSTBOOT),true)
install-firstboot: install-firstboot-real
else
install-firstboot: ;
endif

.PHONY: install-initial-setup
ifeq ($(INSTALL_INITIAL_SETUP),true)
install-initial-setup: install-initial-setup-real
else
install-initial-setup: ;
endif

.PHONY: install-post-boot
install-post-boot: install-firstboot install-initial-setup

.PHONY: install
install: install-files install-po install-conf install-help-files install-plugins-conf

set-versions:
	sed -e 's/RPM_VERSION/$(VERSION)/g' -e 's/GTK_VERSION/$(GTK_VERSION)/g' $(SRC_DIR)/version.py.in > $(SRC_DIR)/version.py
	sed -e 's/RPM_VERSION/$(VERSION)/g' $(RCT_SRC_DIR)/version.py.in > $(RCT_SRC_DIR)/version.py

install-po: compile-po
	install -d $(RHSM_LOCALE_DIR)
	cp -R po/build/* $(RHSM_LOCALE_DIR)/

clean-versions:
	rm -rf $(SRC_DIR)/version.py
	rm -rf $(RCT_SRC_DIR)/version.py

install-glade:
	install -d $(GLADE_INST_DIR)
	install -m 644 $(SRC_DIR)/gui/data/glade/*.glade $(SUBMAN_INST_DIR)/gui/data/glade/

install-ui:
	install -d $(UI_INST_DIR)
	install -m 644 $(SRC_DIR)/gui/data/ui/*.ui $(SUBMAN_INST_DIR)/gui/data/ui/

# We could choose here, but it doesn't matter.
install-gui: install-glade install-ui

install-files: set-versions dbus-service-install desktop-files install-plugins install-post-boot install-ga install-gui
	install -d $(PYTHON_INST_DIR)/gui
	install -d $(PYTHON_INST_DIR)/gui/data/icons
	install -d $(PYTHON_INST_DIR)/branding
	install -d $(PYTHON_INST_DIR)/model
	install -d $(PYTHON_INST_DIR)/migrate
	install -d $(PYTHON_INST_DIR)/plugin
	install -d $(PYTHON_INST_DIR)/plugin/ostree
	install -d $(PYTHON_INST_DIR)/plugin
	install -d $(PYTHON_INST_DIR)/plugin/ostree
	install -d $(PREFIX)/$(INSTALL_DIR)/locale/
	install -d $(PREFIX)/usr/lib/yum-plugins/
	install -d $(PREFIX)/usr/sbin
	install -d $(PREFIX)/etc/rhsm
	install -d $(PREFIX)/etc/rhsm/facts
	install -d $(PREFIX)/etc/xdg/autostart
	install -d $(PREFIX)/etc/cron.daily
	install -d $(PREFIX)/etc/pam.d
	install -d $(PREFIX)/etc/logrotate.d
	install -d $(PREFIX)/etc/security/console.apps
	install -d $(PREFIX)/etc/yum/pluginconf.d/
	install -d $(PREFIX)/$(INSTALL_DIR)/man/man5/
	install -d $(PREFIX)/$(INSTALL_DIR)/man/man8/
	install -d $(PREFIX)/$(INSTALL_DIR)/applications
	install -d $(PREFIX)/var/log/rhsm
	install -d $(PREFIX)/var/spool/rhsm/debug
	install -d $(PREFIX)/var/run/rhsm
	install -d $(PREFIX)/var/lib/rhsm/facts
	install -d $(PREFIX)/var/lib/rhsm/packages
	install -d $(PREFIX)/var/lib/rhsm/cache
	install -d $(PREFIX)/usr/bin
	install -d $(PREFIX)/etc/rc.d/init.d
	install -d $(PREFIX)/usr/share/icons/hicolor/16x16/apps
	install -d $(PREFIX)/usr/share/icons/hicolor/22x22/apps
	install -d $(PREFIX)/usr/share/icons/hicolor/24x24/apps
	install -d $(PREFIX)/usr/share/icons/hicolor/32x32/apps
	install -d $(PREFIX)/usr/share/icons/hicolor/48x48/apps
	install -d $(PREFIX)/usr/share/icons/hicolor/96x96/apps
	install -d $(PREFIX)/usr/share/icons/hicolor/256x256/apps
	install -d $(PREFIX)/usr/share/icons/hicolor/scalable/apps
	install -d $(PREFIX)/usr/share/rhsm/subscription_manager/gui/firstboot
	install -d $(PREFIX)/usr/share/appdata


	install -d $(PREFIX)/usr/libexec
	install -m 755 $(DAEMONS_SRC_DIR)/rhsmcertd-worker.py \
		$(PREFIX)/usr/libexec/rhsmcertd-worker


	install -m 644 -p $(SRC_DIR)/*.py $(PYTHON_INST_DIR)/
	install -m 644 -p $(SRC_DIR)/gui/*.py $(PYTHON_INST_DIR)/gui
	install -m 644 -p $(SRC_DIR)/migrate/*.py $(PYTHON_INST_DIR)/migrate
	install -m 644 -p $(SRC_DIR)/branding/*.py $(PYTHON_INST_DIR)/branding
	install -m 644 -p $(SRC_DIR)/model/*.py $(PYTHON_INST_DIR)/model
	install -m 644 -p $(SRC_DIR)/plugin/*.py $(PYTHON_INST_DIR)/plugin
	install -m 644 -p src/plugins/*.py $(PREFIX)/usr/lib/yum-plugins/

	install -m 644 etc-conf/subscription-manager-gui.completion.sh $(PREFIX)/etc/bash_completion.d/subscription-manager-gui


	if [ "$(INSTALL_OSTREE_PLUGIN)" = "true" ] ; then \
		install -m 644 -p $(SRC_DIR)/plugin/ostree/*.py $(SUBMAN_INST_DIR)/plugin/ostree ; \
	fi

	#icons
	install -m 644 $(SRC_DIR)/gui/data/icons/hicolor/16x16/apps/*.png \
		$(PREFIX)/usr/share/icons/hicolor/16x16/apps
	install -m 644 $(SRC_DIR)/gui/data/icons/hicolor/22x22/apps/*.png \
		$(PREFIX)/usr/share/icons/hicolor/22x22/apps
	install -m 644 $(SRC_DIR)/gui/data/icons/hicolor/24x24/apps/*.png \
		$(PREFIX)/usr/share/icons/hicolor/24x24/apps
	install -m 644 $(SRC_DIR)/gui/data/icons/hicolor/32x32/apps/*.png \
		$(PREFIX)/usr/share/icons/hicolor/32x32/apps
	install -m 644 $(SRC_DIR)/gui/data/icons/hicolor/48x48/apps/*.png \
		$(PREFIX)/usr/share/icons/hicolor/48x48/apps
	install -m 644 $(SRC_DIR)/gui/data/icons/hicolor/96x96/apps/*.png \
		$(PREFIX)/usr/share/icons/hicolor/96x96/apps
	install -m 644 $(SRC_DIR)/gui/data/icons/hicolor/256x256/apps/*.png \
		$(PREFIX)/usr/share/icons/hicolor/256x256/apps
	install -m 644 $(SRC_DIR)/gui/data/icons/hicolor/scalable/apps/*.svg \
		$(PREFIX)/usr/share/icons/hicolor/scalable/apps
	install -m 644 $(SRC_DIR)/gui/data/icons/*.svg \
		$(SUBMAN_INST_DIR)/gui/data/icons

	install bin/subscription-manager $(PREFIX)/usr/sbin
	install bin/rhn-migrate-classic-to-rhsm  $(PREFIX)/usr/sbin
	install bin/subscription-manager-gui $(PREFIX)/usr/sbin
	install bin/rhsmcertd $(PREFIX)/usr/bin

	# Set up rhsmcertd daemon. If installing on Fedora 17+ or RHEL 7+
	# we prefer systemd over sysv as this is the new trend.
	if [ $(OS) = Fedora ] ; then \
		if [ $(OS_VERSION) -lt 17 ]; then \
			install etc-conf/rhsmcertd.init.d \
				$(PREFIX)/etc/rc.d/init.d/rhsmcertd; \
		else \
			install -d $(SYSTEMD_INST_DIR); \
			install -d $(PREFIX)/usr/lib/tmpfiles.d; \
			install etc-conf/rhsmcertd.service $(SYSTEMD_INST_DIR); \
			install etc-conf/subscription-manager.conf.tmpfiles \
				$(PREFIX)/usr/lib/tmpfiles.d/subscription-manager.conf; \
		fi; \
	else \
		if [ $(OS_VERSION) -lt 7 ]; then \
			install etc-conf/rhsmcertd.init.d \
				$(PREFIX)/etc/rc.d/init.d/rhsmcertd; \
		else \
			install -d $(SYSTEMD_INST_DIR); \
			install -d $(PREFIX)/usr/lib/tmpfiles.d; \
			install etc-conf/rhsmcertd.service $(SYSTEMD_INST_DIR); \
			install etc-conf/subscription-manager.conf.tmpfiles \
				$(PREFIX)/usr/lib/tmpfiles.d/subscription-manager.conf; \
		fi; \
	fi; \


	install -m 644 man/rhn-migrate-classic-to-rhsm.8 $(PREFIX)/$(INSTALL_DIR)/man/man8/
	install -m 644 man/rhsmcertd.8 $(PREFIX)/$(INSTALL_DIR)/man/man8/
	install -m 644 man/rhsm-icon.8 $(PREFIX)/$(INSTALL_DIR)/man/man8/
	install -m 644 man/subscription-manager.8 $(PREFIX)/$(INSTALL_DIR)/man/man8/
	install -m 644 man/subscription-manager-gui.8 $(PREFIX)/$(INSTALL_DIR)/man/man8/
	install -m 644 man/rct.8 $(PREFIX)/$(INSTALL_DIR)/man/man8/
	install -m 644 man/rhsm-debug.8 $(PREFIX)/$(INSTALL_DIR)/man/man8/
	install -m 644 man/rhsm.conf.5 $(PREFIX)/$(INSTALL_DIR)/man/man5/

	install -m 644 etc-conf/rhsm-icon.desktop \
		$(PREFIX)/etc/xdg/autostart;\
	install bin/rhsm-icon $(PREFIX)/usr/bin;\

	install -m 700 etc-conf/rhsmd.cron \
		$(PREFIX)/etc/cron.daily/rhsmd
	install -m 644 etc-conf/subscription-manager-gui.desktop \
		$(PREFIX)/$(INSTALL_DIR)/applications

	ln -sf /usr/bin/consolehelper $(PREFIX)/usr/bin/subscription-manager-gui
	ln -sf /usr/bin/consolehelper $(PREFIX)/usr/bin/subscription-manager

	install -m 644 etc-conf/subscription-manager-gui.pam \
		$(PREFIX)/etc/pam.d/subscription-manager-gui
	install -m 644 etc-conf/subscription-manager-gui.console \
		$(PREFIX)/etc/security/console.apps/subscription-manager-gui

	install -m 644 etc-conf/subscription-manager.pam \
		$(PREFIX)/etc/pam.d/subscription-manager
	install -m 644 etc-conf/subscription-manager.console \
		$(PREFIX)/etc/security/console.apps/subscription-manager

	install -d $(RCT_INST_DIR)
	install -m 644 -p $(RCT_SRC_DIR)/*.py $(RCT_INST_DIR)
	install bin/rct $(PREFIX)/usr/bin

	install -d $(RD_INST_DIR)
	install -m 644 -p $(RD_SRC_DIR)/*.py $(RD_INST_DIR)
	install bin/rhsm-debug $(PREFIX)/usr/bin


desktop-files: etc-conf/rhsm-icon.desktop \
				etc-conf/subscription-manager-gui.desktop

%.desktop: %.desktop.in po
	intltool-merge -d po $< $@

check:
	python setup.py -q nosetests -c playpen/noserc.dev

smoke:
	test/smoke.sh

coverage: coverage-jenkins

coverage-html: coverage-jenkins

.PHONY: coverage-jenkins
coverage-jenkins:
	python setup.py -q nosetests -c playpen/noserc.ci

#
# gettext, po files, etc
#

po/POTFILES.in:
	# generate the POTFILES.in file expected by intltool. it wants one
	# file per line, but we're lazy.
	find $(SRC_DIR)/ $(RCT_SRC_DIR) $(RD_SRC_DIR) $(DAEMONS_SRC_DIR) $(YUM_PLUGINS_SRC_DIR) -name "*.py" > po/POTFILES.in
	find $(SRC_DIR)/gui/data/ -name "*.glade" >> po/POTFILES.in
	find $(BIN_DIR) -name "*-to-rhsm" >> po/POTFILES.in
	find $(BIN_DIR) -name "subscription-manager*" >> po/POTFILES.in
	find $(BIN_DIR) -name "rct" >> po/POTFILES.in
	find $(BIN_DIR) -name "rhsm-debug" >> po/POTFILES.in
	find src/ -name "*.c" >> po/POTFILES.in
	find etc-conf/ -name "*.desktop.in" >> po/POTFILES.in
	find $(RCT_SRC_DIR)/ -name "*.py" >> po/POTFILES.in
	find $(RD_SRC_DIR)/ -name "*.py" >> po/POTFILES.in
	echo $$(echo `pwd`|rev | sed -r 's|[^/]+|..|g') | sed 's|$$|$(shell find /usr/lib*/python2* -name "optparse.py")|' >> po/POTFILES.in

.PHONY: po/POTFILES.in %.desktop

gettext: po/POTFILES.in
	# Extract strings from our source files. any comments on the line above
	# the string marked for translation beginning with "translators" will be
	# included in the pot file.
	cd po && \
	intltool-update --pot -g keys

update-po:
	for f in $(shell find po/ -name "*.po") ; do \
		msgmerge -N --backup=none -U $$f po/keys.pot ; \
	done

uniq-po:
	for f in $(shell find po/ -name "*.po") ; do \
		msguniq $$f -o $$f ; \
	done

# Compile translations
compile-po:
	@ echo -n "Compiling po files for: " ; \
	for lang in $(basename $(notdir $(wildcard po/*.po))) ; do \
		echo -n "$$lang " ; \
		mkdir -p po/build/$$lang/LC_MESSAGES/ ; \
		msgfmt --check-format --check-domain -o po/build/$$lang/LC_MESSAGES/rhsm.mo po/$$lang.po ; \
	done ; \
	echo ;

# just run a check to make sure these compile
polint:
	# This is just informational, most zanata po files dont pass
	for lang in $(basename $(notdir $(wildcard po/*.po))) ; do \
		msgfmt -c -o /dev/null po/$$lang.po ; \
	done ;

just-strings:
	-@ scripts/just_strings.py po/keys.pot

zanata-pull:
	pushd po && zanata pull --transdir . && popd

zanata-push:
	pushd po; \
	ls -al; \
	if [ -z $(shell find -name "*.pot" | grep -v keys.pot) ] ; then \
		zanata push ; \
	else 	\
		echo "po/ has more than one *.pot file, please clean up" ; \
	fi; \
	popd

# do all the zanata bits
zanata: gettext zanata-push zanata-pull update-po
	echo "# pofiles should be ready to commit and push"

# generate a en_US.po with long strings for testing
gen-test-long-po:
	-@ scripts/gen_test_en_po.py --long po/en_US.po

#
# checkers, linters, etc
#

.PHONY: pylint
pylint:
	@PYTHONPATH="src/:/usr/share/rhn:../python-rhsm/src/:/usr/share/rhsm" python setup.py lint

.PHONY: tablint
tablint:
	@! GREP_COLOR='7;31' grep --color -nP "^\W*\t" $(STYLEFILES)

.PHONY: trailinglint
trailinglint:
	@! GREP_COLOR='7;31'  grep --color -nP "[ \t]$$" $(STYLEFILES)

.PHONY: whitespacelint
whitespacelint: tablint trailinglint

# look for things that are likely debugging code left in by accident
.PHONY: debuglint
debuglint:
	@! GREP_COLOR='7;31' grep --color -nP "pdb.set_trace|pydevd.settrace|import ipdb|import pdb|import pydevd" $(STYLEFILES)

# find widgets used via get_widget
# find widgets used as passed to init of SubscriptionManagerTab,
# find the widgets we actually find in the glade files
# see if any used ones are not defined
.PHONY: find-missing-signals
find-missing-widgets:
	@TMPFILE=`mktemp` || exit 1; \
	USED_WIDGETS=`mktemp` ||exit 1; \
	DEFINED_WIDGETS=`mktemp` ||exit 1; \
	perl -n -e "if (/get_widget\([\'|\"](.*?)[\'|\"]\)/) { print(\"\$$1\n\")}" $(STYLEFILES) > $$USED_WIDGETS; \
	pcregrep -h -o  -M  "(?:widgets|widget_names) = \[.*\s*.*?\s*.*\]" $(STYLEFILES) | perl -0 -n -e "my @matches = /[\'|\"](.*?)[\'|\"]/sg ; $$,=\"\n\"; print(@matches);" >> $$USED_WIDGETS; \
	perl -n -e "if (/<object class=\".*?\" id=\"(.*?)\">/) { print(\"\$$1\n\")}" $(GLADEFILES) $(UIFILES) > $$DEFINED_WIDGETS; \
	while read line; do grep -F "$$line" $$DEFINED_WIDGETS > /dev/null ; STAT="$$?"; if [ "$$STAT" -ne "0" ] ; then echo "$$line"; fi;  done < $$USED_WIDGETS | tee $$TMPFILE; \
	! test -s $$TMPFILE

# find any signals defined in glade and make sure we use them somewhere
# this would be better if we could statically extract the used signals from
# the code.
.PHONY: find-missing-signals
find-missing-signals:
	@TMPFILE=`mktemp` || exit 1; \
	DEFINED_SIGNALS=`mktemp` ||exit 1; \
	perl -n -e "if (/<signal name=\"(.*?)\" handler=\"(.*?)\"/) { print(\"\$$2\n\")}" $(GLADEFILES) $(UIFILES) > $$DEFINED_SIGNALS; \
	while read line; do grep -F  "$$line" $(PYFILES) > /dev/null; STAT="$$?"; if [ "$$STAT" -ne "0" ] ; then echo "$$line"; fi;  done < $$DEFINED_SIGNALS | tee $$TMPFILE; \
	! test -s $$TMPFILE
# try to clean up the "swapped=no" signal thing in
# glade files, since rhel6 hates it
# also remove unneeded 'orientation' property for vbox's
# since it causes warnings on RHEL5
fix-glade:
	perl -pi -e 's/(swapped=\".*?\")//' $(GLADEFILES)
	perl -pi -e 's/^.*property\s*name=\"orientation\">vertical.*$$//' $(GLADEFILES)


# look for python string formats that are known to break xgettext
# namely constructs of the forms: _("a" + "b")
#                                 _("a" + \
#                                   "b")
#  also look for _(a) usages
.PHONY: gettext_lint
gettext_lint:
	@TMPFILE=`mktemp` || exit 1; \
	pcregrep -n --color=auto -M "_\(.*[\'|\"].*?[\'|\"]\s*\+.*?(?s)\s*[\"|\'].*?(?-s)[\"|\'].*?\)"  $(STYLEFILES) | tee $$TMPFILE; \
	pcregrep -n --color=auto -M "[^_]_\([^ru\'\"].*?[\'\"]?\)" $(STYLEFILES) | tee $$TMPFILE; \
	! test -s $$TMPFILE

#see bz #826874, causes issues on older libglade
.PHONY: gladelint
gladelint:
	@TMPFILE=`mktemp` || exit 1; \
	grep -nP  "swapped=\"no\"" $(GLADEFILES) | tee $$TMPFILE; \
    grep -nP "property name=\"orientation\"" $(GLADEFILES) | tee $$TMPFILE; \
	! test -s $$TMPFILE

.PHONY: flake8
flake8:
	@python setup.py -q flake8 -q


.PHONY: rpmlint
rpmlint:
	@TMPFILE=`mktemp` || exit 1; \
	rpmlint -f rpmlint.config subscription-manager.spec | grep -v "^.*packages and .* specfiles checked\;" | tee $$TMPFILE; \
	! test -s $$TMPFILE

# We target python 2.6, hence -m 2.7 is the earliest python features to warn about use of.
# See https://github.com/alikins/pyqver for pyqver.
# Since plugin/ostree is for python 2.7+ systems only, we can ignore the warning there.
.PHONY: versionlint
versionlint:
	@TMPFILE=`mktemp` || exit 1; \
	pyqver2.py -m 2.7 -l $(STYLEFILES) | grep -v hashlib | grep -v plugin/ostree.*check_output | tee $$TMPFILE; \
	! test -s $$TMPFILE

.PHONY: stylish
stylish: whitespacelint flake8 versionlint rpmlint debuglint gettext_lint

# uncommon, so move to just letting jenkins run these by default
.PHONY: stylish-harder
stylish-harder: gladelint find-missing-widgets find-missing-signals

.PHONY: install-pip-requirements
install-pip-requirements:
	@pip install -r test-requirements.txt

.PHONY: jenkins
jenkins: install-pip-requirements build stylish stylish-harder coverage-jenkins



stylefiles:
	@echo $(STYLEFILES)
