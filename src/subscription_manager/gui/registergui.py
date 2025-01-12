#
# Registration dialog/wizard
#
# Copyright (c) 2011 Red Hat, Inc.
#
# This software is licensed to you under the GNU General Public License,
# version 2 (GPLv2). There is NO WARRANTY for this software, express or
# implied, including the implied warranties of MERCHANTABILITY or FITNESS
# FOR A PARTICULAR PURPOSE. You should have received a copy of GPLv2
# along with this software; if not, see
# http://www.gnu.org/licenses/old-licenses/gpl-2.0.txt.
#
# Red Hat trademarks are not licensed under GPLv2. No permission is
# granted to use or replicate Red Hat trademarks that are incorporated
# in this software or its documentation.
#

import gettext
import logging
import Queue
import re
import socket
import sys
import threading


from subscription_manager.ga import Gtk as ga_Gtk
from subscription_manager.ga import GObject as ga_GObject

import rhsm.config as config
from rhsm.utils import ServerUrlParseError
from rhsm.connection import GoneException

from subscription_manager.branding import get_branding
from subscription_manager.action_client import ActionClient
from subscription_manager.gui import networkConfig
from subscription_manager.gui import widgets
from subscription_manager.injection import IDENTITY, PLUGIN_MANAGER, require, \
        INSTALLED_PRODUCTS_MANAGER, PROFILE_MANAGER
from subscription_manager import managerlib
from subscription_manager.utils import is_valid_server_info, MissingCaCertException, \
        parse_server_info, restart_virt_who

from subscription_manager.gui.utils import handle_gui_exception, show_error_window
from subscription_manager.gui.autobind import DryRunResult, \
        ServiceLevelNotSupportedException, AllProductsCoveredException, \
        NoProductsException
from subscription_manager.gui.messageWindow import InfoDialog, OkDialog
from subscription_manager.jsonwrapper import PoolWrapper

_ = lambda x: gettext.ldgettext("rhsm", x)

gettext.textdomain("rhsm")

#Gtk.glade.bindtextdomain("rhsm")

#Gtk.glade.textdomain("rhsm")

log = logging.getLogger('rhsm-app.' + __name__)

CFG = config.initConfig()

REGISTERING = 0
SUBSCRIBING = 1
state = REGISTERING


def get_state():
    global state
    return state


def set_state(new_state):
    global state
    state = new_state

DONT_CHANGE = -2
PROGRESS_PAGE = -1
CHOOSE_SERVER_PAGE = 0
ACTIVATION_KEY_PAGE = 1
CREDENTIALS_PAGE = 2
OWNER_SELECT_PAGE = 3
ENVIRONMENT_SELECT_PAGE = 4
PERFORM_REGISTER_PAGE = 5
SELECT_SLA_PAGE = 6
CONFIRM_SUBS_PAGE = 7
PERFORM_SUBSCRIBE_PAGE = 8
REFRESH_SUBSCRIPTIONS_PAGE = 9
INFO_PAGE = 10
DONE_PAGE = 11
FINISH = 100

REGISTER_ERROR = _("<b>Unable to register the system.</b>") + \
    "\n%s\n" + \
    _("Please see /var/log/rhsm/rhsm.log for more information.")


# from old smolt code.. Force glibc to call res_init()
# to rest the resolv configuration, including reloading
# resolv.conf. This attempt to handle the case where we
# start up with no networking, fail name resolution calls,
# and cache them for the life of the process, even after
# the network starts up, and for dhcp, updates resolv.conf
def reset_resolver():
    """Attempt to reset the system hostname resolver.
    returns 0 on success, or -1 if an error occurs."""
    try:
        import ctypes
        try:
            resolv = ctypes.CDLL("libc.so.6")
            r = resolv.__res_init()
        except (OSError, AttributeError):
            log.warn("could not find __res_init in libc.so.6")
            r = -1
        return r
    except ImportError:
        # If ctypes isn't supported (older versions of python for example)
        # Then just don't do anything
        pass
    except Exception, e:
        log.warning("reset_resolver failed: %s", e)
        pass


class RegistrationBox(widgets.SubmanBaseWidget):
    gui_file = "registration_box"


class RegisterScreen(widgets.SubmanBaseWidget):
    """
    Registration Widget Screen

    RegisterScreen is the parent widget of registration screens, and
    also the base class of the firstboot rhsm_module.

    RegisterScreen has a list of Screen subclasses.

    Screen subclasses can be Screen, NonGuiScreen, or GuiScreen
    classes. Only GuiScreen classes are user visible. NonGuiScreen
    and subclasses are used for state transitions (a between screens
    check for pools, for example)

    The rhsmModule.apply() runs RegisterScreen.register().
    RegisterScreen.register runs the current screens .apply().

    A Screen.apply() will return the index of the next screen that
    should be invoked (which may be a different screen, the same screen,
    or the special numbers for DONT_CHANGE and FINISH.)

    In firstboot, calling the firstboot modules .apply() results in calling
    rhsm_module.moduleClass.apply() which calls the first Screen.apply()
    (also self._current_screen).

    After the Screen.apply(), RegisterScreen.register checks it's return
    for DONT_CHANGE or FINISH.

    If the apply returns a screen index, then the Screen.post() is called.
    The return value is ignored.

    The RegisterScreen.register calls RegisterScreen.run_pre() on the
    screen index that the current_screen .apply() returned(i.e. the
    next screen).

    run_pre() checks that it's arg (the result of above apply(), what
    is still currently the next screen) is not DONT_CHANGE/FINISH.

    If not, then it calls self._set_screen() which updates
    self._current_screen to point to the next screen.

    run_pre() then calls the new current_screens's .pre()

    .register()
        next_screen = current_screen.apply()
        current_screen.post()
        RegisterScreen.run_pre(next_screen)
        RegisterScreen._set_screen(next_screen)
            current_screen = next_screen

            Then if current_screen is a gui screen, the visible
            gui will update with the new widgets.

        The new current_screen has its pre() method invoked. pre()
        methods may return an async representing that a request
        has been called and a callback registered. If that's the case,
        then RegisterScreen._set_screen() sets the current screen
        to a progress screen.

    The return value of RegisterScreen.run_pre() is ignored, and
    RegisterScreen.register() returns False.

    This returns to rhsm_login.apply(), where valid_registration is
    set to the return value. valid_registration=True indicates a
    succesful registration

    If valid_registration=True, we are basically done with registeration.
    But rhsm_login can't return from apply() yet, since that could
    potential lead to firstboot ending if it's the last or only module.

    gtk main loop iterations are run, mostly to let any threads finish
    up and any idle loop thread watchers to dry up.

    The return value of rhsm_login.apply() at this point is actualy
    the _apply_result instance variable. Register Screens() are expected
    to set this by calling their finish_registration() method. For
    subscription-manager-gui that means RegisterScreen.finish_registration,
    usually access as a Screens() self._parent.finish_registration.

    For firstboot screens, self._parent will be rhsm_module.moduleClass
    (also a subclass of RegisterScreen).

    rhsm_module.finish_registration() will check the "failed" boolean,
    and either return to a Screen() (CredentialsPage, atm). Or if
    failed=True, it will also call RegisterScreen.finish_registration(),
    that closes the gui window.

    The UI flow is a result of the order of RegisterScreen._screens,
    and the screen indexes returned by Screen.apply().

    But, between the Screen activity call also change the flow, most
    notably the results of any async calls and callbacks invoked from
    the screens .pre()

    A common case is the async callbacks error handling calling
    self._parent.finish_registration(failed=True)

    The async callback can also call RegisterScreen.pre_done() to send the
    UI to a different screen. RHSM api call results that indicate multiple
    choices for a sub would send flow to a chooseSub GuiScreen vs a
    NonGuiScreen for attaching a sub, for example.

    RegisterScreen.run_pre schedules async jobs, they get queued, and
    wait for their callbacks. The callbacks then can use pre_done()
    to finish the tasks the run_pre started. Typicaly the UI will
    see the Progress screens in the meantime.

    If going to screen requires an async task, run_pre starts it by
    calling the new screens pre(), setting that screen to current (_set_screen),
    and then setting the GuiScreen to the progress screens. Screen
    transitions that don't need async tasks just return nothing from
    their pre() and go to the next screen in the order in self._screens.

    Note the the flow of firstboot through multiple modules is driven
    by the return value of rhsm_login.apply(). firstboot itself maintains
    a list of modules and a an ordered list of them. True goes to the
    next screen, False stays. Except for RHEL6, where it is the opposite.

    As of RHEL7.0+, none of that matters much, since rhsm_login is the
    only module in firstboot.

    """

    widget_names = ['register_dialog', 'register_notebook',
                    'register_progressbar', 'register_details_label',
                    'cancel_button', 'register_button', 'progress_label',
                    'dialog_vbox6']
    gui_file = "registration"
    __gtype_name__ = 'RegisterScreen'

    def __init__(self, backend, facts=None, parent=None, callbacks=None):
        """
        Callbacks will be executed when registration status changes.
        """
        super(RegisterScreen, self).__init__()

        self.backend = backend
        self.identity = require(IDENTITY)
        self.facts = facts
        self.parent = parent
        self.callbacks = callbacks or []

        self.async = AsyncBackend(self.backend)

        callbacks = {"on_register_cancel_button_clicked": self.cancel,
                     "on_register_button_clicked": self._on_register_button_clicked,
                     "hide": self.cancel,
                     "on_register_dialog_delete_event": self._delete_event}
        self.connect_signals(callbacks)

        self.window = self.register_dialog
        self.register_dialog.set_transient_for(self.parent)

        screen_classes = [ChooseServerScreen, ActivationKeyScreen,
                          CredentialsScreen, OrganizationScreen,
                          EnvironmentScreen, PerformRegisterScreen,
                          SelectSLAScreen, ConfirmSubscriptionsScreen,
                          PerformSubscribeScreen, RefreshSubscriptionsScreen,
                          InfoScreen, DoneScreen]
        self._screens = []
        for screen_class in screen_classes:
            screen = screen_class(self, self.backend)
            self._screens.append(screen)
            if screen.needs_gui:
                screen.index = self.register_notebook.append_page(
                        screen.container, tab_label=None)

        self._current_screen = CHOOSE_SERVER_PAGE

        # values that will be set by the screens
        self.username = None
        self.consumername = None
        self.activation_keys = None
        self.owner_key = None
        self.environment = None
        self.current_sla = None
        self.dry_run_result = None
        self.skip_auto_bind = False

        # XXX needed by firstboot
        self.password = None

        # FIXME: a 'done' signal maybe?
        # initial_setup needs to be able to make this empty
        self.close_window_callback = self._close_window_callback

    def initialize(self):
        # Ensure that we start on the first page and that
        # all widgets are cleared.
        self._set_initial_screen()

        self._set_navigation_sensitive(True)
        self._clear_registration_widgets()
        self.timer = ga_GObject.timeout_add(100, self._timeout_callback)

    def show(self):
        # initial-setup module skips this, since it results in a
        # new top level window that isn't reparented to the initial-setup
        # screen.
        self.register_dialog.show()

    def _set_initial_screen(self):
        target = self._get_initial_screen()
        self._set_screen(target)

    def _get_initial_screen(self):
        return CHOOSE_SERVER_PAGE

    # for subman gui, we don't need to switch screens on error
    # but for firstboot, we will go back to the info screen if
    # we have it.
    def error_screen(self):
        return DONT_CHANGE

    # FIXME: This exists because standalone gui needs to update the nav
    #        buttons in it's own top level window, while firstboot needs to
    #        update the buttons in the main firstboot window. Firstboot version
    #        has additional logic for rhel5/rhel6 differences.
    def _set_navigation_sensitive(self, sensitive):
        self.cancel_button.set_sensitive(sensitive)
        self.register_button.set_sensitive(sensitive)

    def _set_screen(self, screen):
        if screen > PROGRESS_PAGE:
            self._current_screen = screen
            if self._screens[screen].needs_gui:
                self._set_register_label(screen)
                self.register_notebook.set_current_page(self._screens[screen].index)
        else:
            self.register_notebook.set_current_page(screen + 1)

        if get_state() == REGISTERING:
            # aka, if this is firstboot
            if not isinstance(self.register_dialog, ga_Gtk.VBox):
                self.register_dialog.set_title(_("System Registration"))
            self.progress_label.set_markup(_("<b>Registering</b>"))
        elif get_state() == SUBSCRIBING:
            if not isinstance(self.register_dialog, ga_Gtk.VBox):
                self.register_dialog.set_title(_("Subscription Attachment"))
            self.progress_label.set_markup(_("<b>Attaching</b>"))

    def _set_register_label(self, screen):
        button_label = self._screens[screen].button_label
        self.register_button.set_label(button_label)

    def _delete_event(self, event, data=None):
        return self.close_window()

    def cancel(self, button):
        self.close_window()

    # callback needs the extra arg, so just a wrapper here
    def _on_register_button_clicked(self, button):
        self.register()

    def register(self):

        result = self._screens[self._current_screen].apply()

        if result == FINISH:
            self.finish_registration()
            return True
        elif result == DONT_CHANGE:
            return False

        self._screens[self._current_screen].post()

        self._run_pre(result)
        return False

    def _run_pre(self, screen):
        # XXX move this into the button handling somehow?
        if screen == FINISH:
            self.finish_registration()
            return

        self._set_screen(screen)
        async = self._screens[self._current_screen].pre()
        if async:
            self._set_navigation_sensitive(False)
            self._set_screen(PROGRESS_PAGE)
            self._set_register_details_label(
                    self._screens[self._current_screen].pre_message)

    def _timeout_callback(self):
        self.register_progressbar.pulse()
        # return true to keep it pulsing
        return True

    def finish_registration(self, failed=False):
        # failed is used by the firstboot subclasses to decide if they should
        # advance the screen or not.
        # XXX it would be cool here to do some async spinning while the
        # main window gui refreshes itself

        # FIXME: subman-gui needs this but initial-setup doesnt
        self.close_window_callback()

        self.emit_consumer_signal()

        ga_GObject.source_remove(self.timer)

    def emit_consumer_signal(self):
        for method in self.callbacks:
            method()

    def done(self):
        self._set_screen(DONE_PAGE)

    def close_window(self):
        if self.close_window_callback:
            self.close_window_callback()

    def _close_window_callback(self):
        set_state(REGISTERING)
        self.register_dialog.hide()
        return True

    def _set_register_details_label(self, details):
        self.register_details_label.set_label("<small>%s</small>" % details)

    def _clear_registration_widgets(self):
        for screen in self._screens:
            screen.clear()

    def pre_done(self, next_screen):
        self._set_navigation_sensitive(True)
        if next_screen == DONT_CHANGE:
            self._set_screen(self._current_screen)
        else:
            self._screens[self._current_screen].post()
            self._run_pre(next_screen)


class AutobindWizard(RegisterScreen):

    def __init__(self, backend, facts, parent):
        super(AutobindWizard, self).__init__(backend, facts, parent)

    def show(self):
        super(AutobindWizard, self).show()
        self._run_pre(SELECT_SLA_PAGE)

    def _get_initial_screen(self):
        return SELECT_SLA_PAGE


class Screen(widgets.SubmanBaseWidget):
    widget_names = ['container']
    gui_file = None

    def __init__(self, parent, backend):
        super(Screen, self).__init__()

        self.pre_message = ""
        self.button_label = _("Register")
        self.needs_gui = True
        self.index = -1
        self._parent = parent
        self._backend = backend

    def pre(self):
        return False

    def apply(self):
        pass

    def post(self):
        pass

    def clear(self):
        pass


class NoGuiScreen(object):

    def __init__(self, parent, backend):
        self._parent = parent
        self._backend = backend
        self.button_label = None
        self.needs_gui = False

    def pre(self):
        return True

    def apply(self):
        return 1

    def post(self):
        pass

    def clear(self):
        pass


class PerformRegisterScreen(NoGuiScreen):

    def __init__(self, parent, backend):
        super(PerformRegisterScreen, self).__init__(parent, backend)
        self.pre_message = _("Registering your system")

    def _on_registration_finished_cb(self, new_account, error=None):
        if error is not None:
            handle_gui_exception(error, REGISTER_ERROR, self._parent.parent)
            self._parent.finish_registration(failed=True)
            return

        try:
            managerlib.persist_consumer_cert(new_account)
            self._parent.backend.cs.force_cert_check()  # Ensure there isn't much wait time

            if self._parent.activation_keys:
                self._parent.pre_done(REFRESH_SUBSCRIPTIONS_PAGE)
            elif self._parent.skip_auto_bind:
                self._parent.pre_done(FINISH)
            else:
                self._parent.pre_done(SELECT_SLA_PAGE)
        except Exception, e:
            handle_gui_exception(e, REGISTER_ERROR, self._parent.parent)
            self._parent.finish_registration(failed=True)

    def pre(self):
        log.info("Registering to owner: %s environment: %s" %
                 (self._parent.owner_key, self._parent.environment))

        self._parent.async.register_consumer(self._parent.consumername,
                                             self._parent.facts,
                                             self._parent.owner_key,
                                             self._parent.environment,
                                             self._parent.activation_keys,
                                             self._on_registration_finished_cb)

        return True


class PerformSubscribeScreen(NoGuiScreen):

    def __init__(self, parent, backend):
        super(PerformSubscribeScreen, self).__init__(parent, backend)
        self.pre_message = _("Attaching subscriptions")

    def _on_subscribing_finished_cb(self, unused, error=None):
        if error is not None:
            handle_gui_exception(error, _("Error subscribing: %s"),
                                 self._parent.parent)
            self._parent.finish_registration(failed=True)
            return

        self._parent.pre_done(FINISH)
        self._parent.backend.cs.force_cert_check()

    def pre(self):
        self._parent.async.subscribe(self._parent.identity.uuid,
                                     self._parent.current_sla,
                                     self._parent.dry_run_result,
                                     self._on_subscribing_finished_cb)

        return True


class ConfirmSubscriptionsScreen(Screen):
    """ Confirm Subscriptions GUI Window """

    widget_names = Screen.widget_names + ['subs_treeview', 'back_button',
                                          'sla_label']

    gui_file = "confirmsubs"

    def __init__(self, parent, backend):

        super(ConfirmSubscriptionsScreen, self).__init__(parent,
                                                         backend)
        self.button_label = _("Attach")

        self.store = ga_Gtk.ListStore(str, bool, str)
        self.subs_treeview.set_model(self.store)
        self.subs_treeview.get_selection().set_mode(ga_Gtk.SelectionMode.NONE)

        self.add_text_column(_("Subscription"), 0, True)

        column = widgets.MachineTypeColumn(1)
        column.set_sort_column_id(1)
        self.subs_treeview.append_column(column)

        self.add_text_column(_("Quantity"), 2)

    def add_text_column(self, name, index, expand=False):
        text_renderer = ga_Gtk.CellRendererText()
        column = ga_Gtk.TreeViewColumn(name, text_renderer, text=index)
        column.set_expand(expand)

        self.subs_treeview.append_column(column)
        column.set_sort_column_id(index)
        return column

    def apply(self):
        return PERFORM_SUBSCRIBE_PAGE

    def set_model(self):
        self._dry_run_result = self._parent.dry_run_result

        # Make sure that the store is cleared each time
        # the data is loaded into the screen.
        self.store.clear()
        self.sla_label.set_markup("<b>" + self._dry_run_result.service_level +
                                  "</b>")

        for pool_quantity in self._dry_run_result.json:
            self.store.append([pool_quantity['pool']['productName'],
                              PoolWrapper(pool_quantity['pool']).is_virt_only(),
                              str(pool_quantity['quantity'])])

    def pre(self):
        self.set_model()
        return False


class SelectSLAScreen(Screen):
    """
    An wizard screen that displays the available
    SLAs that are provided by the installed products.
    """
    widget_names = Screen.widget_names + ['product_list_label',
                                          'sla_radio_container',
                                          'owner_treeview']
    gui_file = "selectsla"

    def __init__(self, parent, backend):
        super(SelectSLAScreen, self).__init__(parent, backend)

        self.pre_message = _("Finding suitable service levels")
        self.button_label = _("Next")

        self._dry_run_result = None

    def set_model(self, unentitled_prod_certs, sla_data_map):
        self.product_list_label.set_text(
                self._format_prods(unentitled_prod_certs))
        group = None
        # reverse iterate the list as that will most likely put 'None' last.
        # then pack_start so we don't end up with radio buttons at the bottom
        # of the screen.
        for sla in reversed(sla_data_map.keys()):
            radio = ga_Gtk.RadioButton(group=group, label=sla)
            radio.connect("toggled", self._radio_clicked, sla)
            self.sla_radio_container.pack_start(radio, expand=False,
                                                fill=False, padding=0)
            radio.show()
            group = radio

        # set the initial radio button as default selection.
        group.set_active(True)

    def apply(self):
        return CONFIRM_SUBS_PAGE

    def post(self):
        self._parent.dry_run_result = self._dry_run_result

    def clear(self):
        child_widgets = self.sla_radio_container.get_children()
        for child in child_widgets:
            self.sla_radio_container.remove(child)

    def _radio_clicked(self, button, service_level):
        if button.get_active():
            self._dry_run_result = self._sla_data_map[service_level]

    def _format_prods(self, prod_certs):
        prod_str = ""
        for i, cert in enumerate(prod_certs):
            log.debug(cert)
            prod_str = "%s%s" % (prod_str, cert.products[0].name)
            if i + 1 < len(prod_certs):
                prod_str += ", "
        return prod_str

    # so much for service level simplifying things
    def _on_get_service_levels_cb(self, result, error=None):
        # The parent for the dialogs is set to the grandparent window
        # (which is MainWindow) because the parent window is closed
        # by finish_registration() after displaying the dialogs.  See
        # BZ #855762.
        if error is not None:
            if isinstance(error[1], ServiceLevelNotSupportedException):
                OkDialog(_("Unable to auto-attach, server does not support service levels."),
                        parent=self._parent.parent)
            elif isinstance(error[1], NoProductsException):
                InfoDialog(_("No installed products on system. No need to attach subscriptions at this time."),
                           parent=self._parent.parent)
            elif isinstance(error[1], AllProductsCoveredException):
                InfoDialog(_("All installed products are covered by valid entitlements. No need to attach subscriptions at this time."),
                           parent=self._parent.parent)
            elif isinstance(error[1], GoneException):
                InfoDialog(_("Consumer has been deleted."), parent=self._parent.parent)
            else:
                log.exception(error)
                handle_gui_exception(error, _("Error subscribing"),
                                     self._parent.parent)
            self._parent.finish_registration(failed=True)
            return

        (current_sla, unentitled_products, sla_data_map) = result

        self._parent.current_sla = current_sla
        if len(sla_data_map) == 1:
            # If system already had a service level, we can hit this point
            # when we cannot fix any unentitled products:
            if current_sla is not None and \
                    not self._can_add_more_subs(current_sla, sla_data_map):
                handle_gui_exception(None,
                                     _("No available subscriptions at "
                                     "the current service level: %s. "
                                     "Please use the \"All Available "
                                     "Subscriptions\" tab to manually "
                                     "attach subscriptions.") % current_sla,
                                    self._parent.parent)
                self._parent.finish_registration(failed=True)
                return

            self._dry_run_result = sla_data_map.values()[0]
            self._parent.pre_done(CONFIRM_SUBS_PAGE)
        elif len(sla_data_map) > 1:
            self._sla_data_map = sla_data_map
            self.set_model(unentitled_products, sla_data_map)
            self._parent.pre_done(DONT_CHANGE)
        else:
            log.info("No suitable service levels found.")
            handle_gui_exception(None,
                                 _("No service level will cover all "
                                 "installed products. Please manually "
                                 "subscribe using multiple service levels "
                                 "via the \"All Available Subscriptions\" "
                                 "tab or purchase additional subscriptions."),
                                 parent=self._parent.parent)
            self._parent.finish_registration(failed=True)

    def pre(self):
        set_state(SUBSCRIBING)
        self._parent.identity.reload()
        self._parent.async.find_service_levels(self._parent.identity.uuid,
                                               self._parent.facts,
                                               self._on_get_service_levels_cb)
        return True

    def _can_add_more_subs(self, current_sla, sla_data_map):
        """
        Check if a system that already has a selected sla can get more
        entitlements at their sla level
        """
        if current_sla is not None:
            result = sla_data_map[current_sla]
            return len(result.json) > 0
        return False


class EnvironmentScreen(Screen):
    widget_names = Screen.widget_names + ['environment_treeview']
    gui_file = "environment"

    def __init__(self, parent, backend):
        super(EnvironmentScreen, self).__init__(parent, backend)

        self.pre_message = _("Fetching list of possible environments")
        renderer = ga_Gtk.CellRendererText()
        column = ga_Gtk.TreeViewColumn(_("Environment"), renderer, text=1)
        self.environment_treeview.set_property("headers-visible", False)
        self.environment_treeview.append_column(column)

    def _on_get_environment_list_cb(self, result_tuple, error=None):
        environments = result_tuple
        if error is not None:
            handle_gui_exception(error, REGISTER_ERROR, self._parent.parent)
            self._parent.finish_registration(failed=True)
            return

        if not environments:
            self._environment = None
            self._parent.pre_done(PERFORM_REGISTER_PAGE)
            return

        envs = [(env['id'], env['name']) for env in environments]
        if len(envs) == 1:
            self._environment = envs[0][0]
            self._parent.pre_done(PERFORM_REGISTER_PAGE)
        else:
            self.set_model(envs)
            self._parent.pre_done(DONT_CHANGE)

    def pre(self):
        self._parent.async.get_environment_list(self._parent.owner_key,
                                                self._on_get_environment_list_cb)
        return True

    def apply(self):
        model, tree_iter = self.environment_treeview.get_selection().get_selected()
        self._environment = model.get_value(tree_iter, 0)
        return PERFORM_REGISTER_PAGE

    def post(self):
        self._parent.environment = self._environment

    def set_model(self, envs):
        environment_model = ga_Gtk.ListStore(str, str)
        for env in envs:
            environment_model.append(env)

        self.environment_treeview.set_model(environment_model)

        self.environment_treeview.get_selection().select_iter(
                environment_model.get_iter_first())


class OrganizationScreen(Screen):
    widget_names = Screen.widget_names + ['owner_treeview']
    gui_file = "organization"

    def __init__(self, parent, backend):
        super(OrganizationScreen, self).__init__(parent, backend)

        self.pre_message = _("Fetching list of possible organizations")

        renderer = ga_Gtk.CellRendererText()
        column = ga_Gtk.TreeViewColumn(_("Organization"), renderer, text=1)
        self.owner_treeview.set_property("headers-visible", False)
        self.owner_treeview.append_column(column)

        self._owner_key = None

    def _on_get_owner_list_cb(self, owners, error=None):
        if error is not None:
            handle_gui_exception(error, REGISTER_ERROR,
                    self._parent.window)
            self._parent.finish_registration(failed=True)
            return

        owners = [(owner['key'], owner['displayName']) for owner in owners]
        # Sort by display name so the list doesn't randomly change.
        owners = sorted(owners, key=lambda item: item[1])

        if len(owners) == 0:
            handle_gui_exception(None,
                                 _("<b>User %s is not able to register with any orgs.</b>") %
                                   (self._parent.username),
                    self._parent.parent)
            self._parent.finish_registration(failed=True)
            return

        if len(owners) == 1:
            self._owner_key = owners[0][0]
            self._parent.pre_done(ENVIRONMENT_SELECT_PAGE)
        else:
            self.set_model(owners)
            self._parent.pre_done(DONT_CHANGE)

    def pre(self):
        self._parent.async.get_owner_list(self._parent.username,
                                          self._on_get_owner_list_cb)
        return True

    def apply(self):
        model, tree_iter = self.owner_treeview.get_selection().get_selected()
        self._owner_key = model.get_value(tree_iter, 0)
        return ENVIRONMENT_SELECT_PAGE

    def post(self):
        self._parent.owner_key = self._owner_key

    def set_model(self, owners):
        owner_model = ga_Gtk.ListStore(str, str)
        for owner in owners:
            owner_model.append(owner)

        self.owner_treeview.set_model(owner_model)

        self.owner_treeview.get_selection().select_iter(
                owner_model.get_iter_first())


class CredentialsScreen(Screen):
    widget_names = Screen.widget_names + ['skip_auto_bind', 'consumer_name',
                                          'account_login', 'account_password',
                                          'registration_tip_label',
                                          'registration_header_label']

    gui_file = "credentials"

    def __init__(self, parent, backend):
        super(CredentialsScreen, self).__init__(parent, backend)

        self._initialize_consumer_name()

        self.registration_tip_label.set_label("<small>%s</small>" %
                                          get_branding().GUI_FORGOT_LOGIN_TIP)

        self.registration_header_label.set_label("<b>%s</b>" %
                                             get_branding().GUI_REGISTRATION_HEADER)

    def _initialize_consumer_name(self):
        if not self.consumer_name.get_text():
            self.consumer_name.set_text(socket.gethostname())

    def _validate_consumername(self, consumername):
        if not consumername:
            show_error_window(_("You must enter a system name."), self._parent.window)
            self.consumer_name.grab_focus()
            return False
        return True

    def _validate_account(self):
        # validate / check user name
        if self.account_login.get_text().strip() == "":
            show_error_window(_("You must enter a login."), self._parent.window)
            self.account_login.grab_focus()
            return False

        if self.account_password.get_text().strip() == "":
            show_error_window(_("You must enter a password."), self._parent.window)
            self.account_password.grab_focus()
            return False
        return True

    def pre(self):
        self.account_login.grab_focus()
        return False

    def apply(self):
        self._username = self.account_login.get_text().strip()
        self._password = self.account_password.get_text().strip()
        self._consumername = self.consumer_name.get_text()
        self._skip_auto_bind = self.skip_auto_bind.get_active()

        if not self._validate_consumername(self._consumername):
            return DONT_CHANGE

        if not self._validate_account():
            return DONT_CHANGE

        self._backend.cp_provider.set_user_pass(self._username, self._password)

        return OWNER_SELECT_PAGE

    def post(self):
        self._parent.username = self._username
        self._parent.password = self._password
        self._parent.consumername = self._consumername
        self._parent.skip_auto_bind = self._skip_auto_bind
        self._parent.activation_keys = None

    def clear(self):
        self.account_login.set_text("")
        self.account_password.set_text("")
        self.consumer_name.set_text("")
        self._initialize_consumer_name()
        self.skip_auto_bind.set_active(False)


class ActivationKeyScreen(Screen):
    widget_names = Screen.widget_names + [
                'activation_key_entry',
                'organization_entry',
                'consumer_entry',
        ]
    gui_file = "activation_key"

    def __init__(self, parent, backend):
        super(ActivationKeyScreen, self).__init__(parent, backend)
        self._initialize_consumer_name()

    def _initialize_consumer_name(self):
        if not self.consumer_entry.get_text():
            self.consumer_entry.set_text(socket.gethostname())

    def apply(self):
        self._activation_keys = self._split_activation_keys(
            self.activation_key_entry.get_text().strip())
        self._owner_key = self.organization_entry.get_text().strip()
        self._consumername = self.consumer_entry.get_text().strip()

        if not self._validate_owner_key(self._owner_key):
            return DONT_CHANGE

        if not self._validate_activation_keys(self._activation_keys):
            return DONT_CHANGE

        if not self._validate_consumername(self._consumername):
            return DONT_CHANGE

        return PERFORM_REGISTER_PAGE

    def _split_activation_keys(self, entry):
        keys = re.split(',\s*|\s+', entry)
        return [x for x in keys if x]

    def _validate_owner_key(self, owner_key):
        if not owner_key:
            show_error_window(_("You must enter an organization."), self._parent.window)
            self.organization_entry.grab_focus()
            return False
        return True

    def _validate_activation_keys(self, activation_keys):
        if not activation_keys:
            show_error_window(_("You must enter an activation key."), self._parent.window)
            self.activation_key_entry.grab_focus()
            return False
        return True

    def _validate_consumername(self, consumername):
        if not consumername:
            show_error_window(_("You must enter a system name."), self._parent.window)
            self.consumer_entry.grab_focus()
            return False
        return True

    def pre(self):
        self.organization_entry.grab_focus()
        return False

    def post(self):
        self._parent.activation_keys = self._activation_keys
        self._parent.owner_key = self._owner_key
        self._parent.consumername = self._consumername
        # Environments aren't used with activation keys so clear any
        # cached value.
        self._parent.environment = None
        self._backend.cp_provider.set_user_pass()


class RefreshSubscriptionsScreen(NoGuiScreen):

    def __init__(self, parent, backend):
        super(RefreshSubscriptionsScreen, self).__init__(parent, backend)
        self.pre_message = _("Attaching subscriptions")

    def _on_refresh_cb(self, error=None):
        if error is not None:
            handle_gui_exception(error, _("Error subscribing: %s"),
                                 self._parent.parent)
            self._parent.finish_registration(failed=True)
            return

        self._parent.pre_done(FINISH)

    def pre(self):
        self._parent.async.refresh(self._on_refresh_cb)
        return True


class ChooseServerScreen(Screen):
    widget_names = Screen.widget_names + ['server_entry', 'proxy_frame',
                                          'default_button', 'choose_server_label',
                                          'activation_key_checkbox']
    gui_file = "choose_server"

    def __init__(self, parent, backend):

        super(ChooseServerScreen, self).__init__(parent, backend)

        self.button_label = _("Next")

        callbacks = {
                "on_default_button_clicked": self._on_default_button_clicked,
                "on_proxy_button_clicked": self._on_proxy_button_clicked,
                "on_server_entry_changed": self._on_server_entry_changed,
            }

        self.connect_signals(callbacks)

        self.network_config_dialog = networkConfig.NetworkConfigDialog()

    def _on_default_button_clicked(self, widget):
        # Default port and prefix are fine, so we can be concise and just
        # put the hostname for RHN:
        self.server_entry.set_text(config.DEFAULT_HOSTNAME)

    def _on_proxy_button_clicked(self, widget):
        # proxy dialog may attempt to resolve proxy and server names, so
        # bump the resolver as well.
        self.reset_resolver()

        self.network_config_dialog.set_parent_window(self._parent.window)
        self.network_config_dialog.show()

    def _on_server_entry_changed(self, widget):
        """
        Disable the activation key checkbox if the user is registering
        to hosted.
        """
        server = self.server_entry.get_text()
        try:
            (hostname, port, prefix) = parse_server_info(server)
            if re.search('subscription\.rhn\.(.*\.)*redhat\.com', hostname):
                sensitive = False
                self.activation_key_checkbox.set_active(False)
            else:
                sensitive = True
            self.activation_key_checkbox.set_sensitive(sensitive)
        except ServerUrlParseError:
            # This may seem like it should be False, but we don't want
            # the checkbox blinking on and off as the user types a value
            # that is first unparseable and then later parseable.
            self.activation_key_checkbox.set_sensitive(True)

    def reset_resolver(self):
        try:
            reset_resolver()
        except Exception, e:
            log.warn("Error from reset_resolver: %s", e)

    def apply(self):
        server = self.server_entry.get_text()
        try:
            (hostname, port, prefix) = parse_server_info(server)
            CFG.set('server', 'hostname', hostname)
            CFG.set('server', 'port', port)
            CFG.set('server', 'prefix', prefix)

            self.reset_resolver()

            try:
                if not is_valid_server_info(hostname, port, prefix):
                    show_error_window(_("Unable to reach the server at %s:%s%s") %
                                      (hostname, port, prefix),
                                      self._parent.window)
                    return self._parent.error_screen()
            except MissingCaCertException:
                show_error_window(_("CA certificate for subscription service has not been installed."),
                                  self._parent.window)
                return self._parent.error_screen()

        except ServerUrlParseError:
            show_error_window(_("Please provide a hostname with optional port and/or prefix: hostname[:port][/prefix]"),
                              self._parent.window)
            return self._parent.error_screen()

        log.debug("Writing server data to rhsm.conf")
        CFG.save()
        self._backend.update()
        if self.activation_key_checkbox.get_active():
            return ACTIVATION_KEY_PAGE
        else:
            return CREDENTIALS_PAGE

    def clear(self):
        # Load the current server values from rhsm.conf:
        current_hostname = CFG.get('server', 'hostname')
        current_port = CFG.get('server', 'port')
        current_prefix = CFG.get('server', 'prefix')

        # No need to show port and prefix for hosted:
        if current_hostname == config.DEFAULT_HOSTNAME:
            self.server_entry.set_text(config.DEFAULT_HOSTNAME)
        else:
            self.server_entry.set_text("%s:%s%s" % (current_hostname,
                    current_port, current_prefix))


class AsyncBackend(object):

    def __init__(self, backend):
        self.backend = backend
        self.plugin_manager = require(PLUGIN_MANAGER)
        self.queue = Queue.Queue()

    def _get_owner_list(self, username, callback):
        """
        method run in the worker thread.
        """
        try:
            retval = self.backend.cp_provider.get_basic_auth_cp().getOwnerList(username)
            self.queue.put((callback, retval, None))
        except Exception:
            self.queue.put((callback, None, sys.exc_info()))

    def _get_environment_list(self, owner_key, callback):
        """
        method run in the worker thread.
        """
        try:
            retval = None
            # If environments aren't supported, don't bother trying to list:
            if self.backend.cp_provider.get_basic_auth_cp().supports_resource('environments'):
                log.info("Server supports environments, checking for "
                         "environment to register with.")
                retval = []
                for env in self.backend.cp_provider.get_basic_auth_cp().getEnvironmentList(owner_key):
                    retval.append(env)
                if len(retval) == 0:
                    raise Exception(_("Server supports environments, but "
                        "none are available."))

            self.queue.put((callback, retval, None))
        except Exception:
            self.queue.put((callback, None, sys.exc_info()))

    def _register_consumer(self, name, facts, owner, env, activation_keys, callback):
        """
        method run in the worker thread.
        """
        try:
            installed_mgr = require(INSTALLED_PRODUCTS_MANAGER)

            self.plugin_manager.run("pre_register_consumer", name=name,
                facts=facts.get_facts())
            retval = self.backend.cp_provider.get_basic_auth_cp().registerConsumer(name=name,
                    facts=facts.get_facts(), owner=owner, environment=env,
                    keys=activation_keys,
                    installed_products=installed_mgr.format_for_server())
            self.plugin_manager.run("post_register_consumer", consumer=retval,
                facts=facts.get_facts())

            require(IDENTITY).reload()
            # Facts and installed products went out with the registration
            # request, manually write caches to disk:
            facts.write_cache()
            installed_mgr.write_cache()

            cp = self.backend.cp_provider.get_basic_auth_cp()

            # In practice, the only time this condition should be true is
            # when we are working with activation keys.  See BZ #888790.
            if not self.backend.cp_provider.get_basic_auth_cp().username and \
                not self.backend.cp_provider.get_basic_auth_cp().password:
                # Write the identity cert to disk
                managerlib.persist_consumer_cert(retval)
                self.backend.update()
                cp = self.backend.cp_provider.get_consumer_auth_cp()

            # FIXME: this looks like we are updating package profile as
            #        basic auth
            profile_mgr = require(PROFILE_MANAGER)
            profile_mgr.update_check(cp, retval['uuid'])

            # We have new credentials, restart virt-who
            restart_virt_who()

            self.queue.put((callback, retval, None))
        except Exception:
            self.queue.put((callback, None, sys.exc_info()))

    def _subscribe(self, uuid, current_sla, dry_run_result, callback):
        """
        Subscribe to the selected pools.
        """
        try:
            if not current_sla:
                log.debug("Saving selected service level for this system.")
                self.backend.cp_provider.get_consumer_auth_cp().updateConsumer(uuid,
                        service_level=dry_run_result.service_level)

            log.info("Binding to subscriptions at service level: %s" %
                    dry_run_result.service_level)
            for pool_quantity in dry_run_result.json:
                pool_id = pool_quantity['pool']['id']
                quantity = pool_quantity['quantity']
                log.debug("  pool %s quantity %s" % (pool_id, quantity))
                self.plugin_manager.run("pre_subscribe", consumer_uuid=uuid,
                                        pool_id=pool_id, quantity=quantity)
                ents = self.backend.cp_provider.get_consumer_auth_cp().bindByEntitlementPool(uuid, pool_id, quantity)
                self.plugin_manager.run("post_subscribe", consumer_uuid=uuid, entitlement_data=ents)
            managerlib.fetch_certificates(self.backend.certlib)
        except Exception:
            # Going to try to update certificates just in case we errored out
            # mid-way through a bunch of binds:
            try:
                managerlib.fetch_certificates(self.backend.certlib)
            except Exception, cert_update_ex:
                log.info("Error updating certificates after error:")
                log.exception(cert_update_ex)
            self.queue.put((callback, None, sys.exc_info()))
            return
        self.queue.put((callback, None, None))

    # This guy is really ugly to run in a thread, can we run it
    # in the main thread with just the network stuff threaded?
    def _find_suitable_service_levels(self, consumer_uuid, facts):

        # FIXME:
        self.backend.update()

        consumer_json = self.backend.cp_provider.get_consumer_auth_cp().getConsumer(
                consumer_uuid)

        if 'serviceLevel' not in consumer_json:
            raise ServiceLevelNotSupportedException()

        owner_key = consumer_json['owner']['key']

        # This is often "", set to None in that case:
        current_sla = consumer_json['serviceLevel'] or None

        if len(self.backend.cs.installed_products) == 0:
            raise NoProductsException()

        if len(self.backend.cs.valid_products) == len(self.backend.cs.installed_products) and \
                len(self.backend.cs.partial_stacks) == 0:
            raise AllProductsCoveredException()

        if current_sla:
            available_slas = [current_sla]
            log.debug("Using system's current service level: %s" %
                    current_sla)
        else:
            available_slas = self.backend.cp_provider.get_consumer_auth_cp().getServiceLevelList(owner_key)
            log.debug("Available service levels: %s" % available_slas)

        # Will map service level (string) to the results of the dry-run
        # autobind results for each SLA that covers all installed products:
        suitable_slas = {}

        # eek, in a thread
        action_client = ActionClient(facts=facts)
        action_client.update()

        for sla in available_slas:
            dry_run_json = self.backend.cp_provider.get_consumer_auth_cp().dryRunBind(consumer_uuid, sla)
            dry_run = DryRunResult(sla, dry_run_json, self.backend.cs)

            # If we have a current SLA for this system, we do not need
            # all products to be covered by the SLA to proceed through
            # this wizard:
            if current_sla or dry_run.covers_required_products():
                suitable_slas[sla] = dry_run
        return (current_sla, self.backend.cs.unentitled_products.values(), suitable_slas)

    def _find_service_levels(self, consumer_uuid, facts, callback):
        """
        method run in the worker thread.
        """
        try:
            suitable_slas = self._find_suitable_service_levels(consumer_uuid, facts)
            self.queue.put((callback, suitable_slas, None))
        except Exception:
            self.queue.put((callback, None, sys.exc_info()))

    def _refresh(self, callback):
        try:
            managerlib.fetch_certificates(self.backend.certlib)
            self.queue.put((callback, None, None))
        except Exception:
            self.queue.put((callback, None, sys.exc_info()))

    def _watch_thread(self):
        """
        glib idle method to watch for thread completion.
        runs the provided callback method in the main thread.
        """
        try:
            (callback, retval, error) = self.queue.get(block=False)
            if error:
                callback(retval, error=error)
            else:
                callback(retval)
            return False
        except Queue.Empty:
            return True

    def get_owner_list(self, username, callback):
        ga_GObject.idle_add(self._watch_thread)
        threading.Thread(target=self._get_owner_list,
                         name="GetOwnerListThread",
                         args=(username, callback)).start()

    def get_environment_list(self, owner_key, callback):
        ga_GObject.idle_add(self._watch_thread)
        threading.Thread(target=self._get_environment_list,
                         name="GetEnvironmentListThread",
                         args=(owner_key, callback)).start()

    def register_consumer(self, name, facts, owner, env, activation_keys, callback):
        """
        Run consumer registration asyncronously
        """
        ga_GObject.idle_add(self._watch_thread)
        threading.Thread(target=self._register_consumer,
                         name="RegisterConsumerThread",
                         args=(name, facts, owner,
                               env, activation_keys, callback)).start()

    def subscribe(self, uuid, current_sla, dry_run_result, callback):
        ga_GObject.idle_add(self._watch_thread)
        threading.Thread(target=self._subscribe,
                         name="SubscribeThread",
                         args=(uuid, current_sla,
                               dry_run_result, callback)).start()

    def find_service_levels(self, consumer_uuid, facts, callback):
        ga_GObject.idle_add(self._watch_thread)
        threading.Thread(target=self._find_service_levels,
                         name="FindServiceLevelsThread",
                         args=(consumer_uuid, facts, callback)).start()

    def refresh(self, callback):
        ga_GObject.idle_add(self._watch_thread)
        threading.Thread(target=self._refresh,
                         name="RefreshThread",
                         args=(callback,)).start()


class DoneScreen(Screen):
    gui_file = "done_box"

    def __init__(self, parent, backend):
        super(DoneScreen, self).__init__(parent, backend)
        self.pre_message = "We are done."


class InfoScreen(Screen):
    """
    An informational screen taken from rhn-client-tools and only displayed
    in firstboot when we're not working alongside that package. (i.e.
    Fedora or RHEL 7 and beyond)

    Also allows the user to skip registration if they wish.
    """
    widget_names = Screen.widget_names + [
                'register_radio',
                'skip_radio',
                'why_register_dialog'
        ]
    gui_file = "registration_info"

    def __init__(self, parent, backend):
        super(InfoScreen, self).__init__(parent, backend)
        self.button_label = _("Next")
        callbacks = {
                "on_why_register_button_clicked":
                    self._on_why_register_button_clicked,
                "on_back_to_reg_button_clicked":
                    self._on_back_to_reg_button_clicked
            }

        # FIXME: self.conntect_signals to wrap self.gui.connect_signals
        self.connect_signals(callbacks)

    def pre(self):
        return False

    def apply(self):
        if self.register_radio.get_active():
            log.debug("Proceeding with registration.")
            return CHOOSE_SERVER_PAGE
        else:
            log.debug("Skipping registration.")
            return FINISH

    def post(self):
        pass

    def _on_why_register_button_clicked(self, button):
        self.why_register_dialog.show()

    def _on_back_to_reg_button_clicked(self, button):
        self.why_register_dialog.hide()
