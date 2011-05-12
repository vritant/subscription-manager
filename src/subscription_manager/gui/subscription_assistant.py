# Subscription Manager Subscription Assistant
#
# Copyright (c) 2010 Red Hat, Inc.
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

import gtk
import gobject
import locale
import gettext
import logging
from datetime import date, datetime

_ = gettext.gettext

log = logging.getLogger('rhsm-app.' + __name__)

import rhsm.certificate as certificate
from subscription_manager import certlib
from subscription_manager.certlib import find_first_invalid_date, CertSorter
from subscription_manager import managerlib
from subscription_manager.gui import storage
from subscription_manager.gui import widgets
from subscription_manager.gui import progress
from subscription_manager import async
from subscription_manager.gui.utils import handle_gui_exception, make_today_now

class MappedListTreeView(gtk.TreeView):

    def add_toggle_column(self, name, column_number, callback):
        toggle_renderer = gtk.CellRendererToggle()
        toggle_renderer.set_property("activatable", True)
        toggle_renderer.set_radio(False)
        toggle_renderer.connect("toggled", callback)
        column = gtk.TreeViewColumn(name, toggle_renderer, active=column_number)
        self.append_column(column)

    def add_column(self, name, column_number, expand=False):
        text_renderer = gtk.CellRendererText()
        column = gtk.TreeViewColumn(name, text_renderer, text=column_number)
        self.store = self.get_model()
        if expand:
            column.set_expand(True)
        else:
            column.add_attribute(text_renderer, 'xalign', self.store['align'])

#        column.add_attribute(text_renderer, 'cell-background',
#                             self.store['background'])

        self.append_column(column)

    def add_date_column(self, name, column_number, expand=False):
        date_renderer = widgets.CellRendererDate()
        column = gtk.TreeViewColumn(name, date_renderer, text=column_number)
        self.store = self.get_model()
        if expand:
            column.set_expand(True)
        else:
            column.add_attribute(date_renderer, 'xalign', self.store['align'])

        self.append_column(column)

class SubscriptionAssistant(widgets.GladeWidget):

    """ Subscription Assistant GUI window. """
    def __init__(self, backend, consumer, facts):
        widget_names = ['subscription_label',
                        'providing_subs_label',
                        'window',
                        'invalid_window',
                        'subscriptions_window',
                        'details_window',
                        'first_invalid_radiobutton',
                        'invalid_date_radiobutton',
                        'subscribe_button',
                        'date_picker_hbox']
        super(SubscriptionAssistant,
                self).__init__('subscription_assistant.glade', widget_names)

        self.backend = backend
        self.consumer = consumer
        self.facts = facts
        self.pool_stash = managerlib.PoolStash(self.backend, self.consumer,
                self.facts)

        self.product_dir = certlib.ProductDirectory()
        self.entitlement_dir = certlib.EntitlementDirectory()

        # Setup initial last valid date:
        self.last_valid_date = self._load_last_valid_date()
        self.cached_date = self.last_valid_date

        invalid_type_map = {'active':bool,
                            'product_name':str,
                            'contract':str,
                            'end_date':str,
                            'entitlement_id':str,
                            'product_id':str,
                            'entitlement':gobject.TYPE_PYOBJECT,
                            'align':float}

        self.window.connect('delete_event', self.hide)
        self.invalid_store = storage.MappedListStore(invalid_type_map)
        self.invalid_treeview = MappedListTreeView(self.invalid_store)

        self.invalid_treeview.get_accessible().set_name(_("Invalid Product List"))

        self.invalid_treeview.add_toggle_column(None,
                                                self.invalid_store['active'],
                                                self._on_invalid_active_toggled)
        self.invalid_treeview.add_column(_("Product"),
                self.invalid_store['product_name'], True)
        self.invalid_treeview.add_date_column(_("End Date"),
                self.invalid_store['end_date'], True)
        self.invalid_treeview.set_model(self.invalid_store)
        self.invalid_window.add(self.invalid_treeview)
        self.invalid_treeview.show()

        subscriptions_type_map = {
            'product_name': str,
            'total_contracts': int,
            'total_subscriptions': int,
            'available_subscriptions': str,
            'pool_id': str, # not displayed, just for lookup
        }

        self.subscriptions_store = storage.MappedListStore(subscriptions_type_map)
        self.subscriptions_treeview = MappedListTreeView(self.subscriptions_store)
        self.subscriptions_treeview.get_accessible().set_name(_("Subscription List"))
        self.subscriptions_treeview.add_column(_("Subscription"),
                self.subscriptions_store['product_name'], True)
        self.subscriptions_treeview.add_column(_("Available Subscriptions"),
                self.subscriptions_store['available_subscriptions'], True)

        self.subscriptions_treeview.set_model(self.subscriptions_store)
        self.subscriptions_treeview.get_selection().connect('changed',
                self._update_sub_details)

        self.subscriptions_window.add(self.subscriptions_treeview)
        self.subscriptions_treeview.show()

        self.sub_details = widgets.SubDetailsWidget(show_contract=False)
        self.details_window.add(self.sub_details.get_widget())

        self.first_invalid_radiobutton.set_active(True)

        self.date_picker = widgets.DatePicker(date.today())
        self.date_picker_hbox.pack_start(self.date_picker, False, False)
        self.date_picker.show_all()

        self.subscribe_button.connect('clicked', self.subscribe_button_clicked)

        self.glade.signal_autoconnect({
            "on_update_button_clicked": self._check_for_date_change,
        })

        self.pb = None
        self.timer = None

    def show(self):
        """
        Called by the main window when this page is to be displayed.
        """
        try:
            self.window.show()
            self._reload_screen()
        except Exception, e:
            handle_gui_exception(e, _("Error displaying Subscription Assistant. Please see /var/log/rhsm/rhsm.log for more information."),
                                 formatMsg=False)

    def set_parent_window(self, window):
        self.window.set_transient_for(window)

    def _reload_callback(self, error=None):
        if self.pb:
            self.pb.hide()
            gobject.source_remove(self.timer)
            self.pb = None
            self.timer = None

        if error:
            handle_gui_exception(error,
                                 _("Unable to search for subscriptions"),
                                 formatMsg=False)
        else:
            self._display_invalid()
            self._display_subscriptions()

    def _reload_screen(self):
        """
        Draws the entire screen, called when window is shown, or something
        changes and we need to refresh.
        """
        log.debug("reloading screen")
        # end date of first subs to expire

        self.last_valid_date = self._load_last_valid_date()

        invalid_date = self._get_invalid_date()
        log.debug("using invalid date: %s" % invalid_date)
        if self.last_valid_date:
            formatted = self.format_date(self.last_valid_date)
            self.subscription_label.set_label("<big><b>%s</b></big>" % \
                    (_("Software entitlements valid through %s") % formatted))
            self.subscription_label.set_line_wrap(True)
            self.subscription_label.connect("size-allocate", self._label_allocate)
            self.first_invalid_radiobutton.set_label(
                    _("%s (first date of invalid entitlements)") % formatted)
            self.providing_subs_label.set_label(
                    _("The following subscriptions will cover the products selected on %s") % invalid_date.strftime("%x"))


        async_stash = async.AsyncPool(self.pool_stash)
        async_stash.refresh(invalid_date, self._reload_callback)

        # show pulsating progress bar while we wait for results
        self.pb = progress.Progress(
                _("Searching for subscriptions. Please wait."))
        self.timer = gobject.timeout_add(100, self.pb.pulse)
        self.pb.set_parent_window(self.window)

    def _label_allocate(self, label, allocation):
        label.set_size_request(allocation.width-2, -1)

    def _check_for_date_change(self, widget):
        """
        Called when the invalid date selection *may* have changed.
        Several signals must be sent out to cover all situations and thus
        multiple may trigger at once. As such we need to store the
        invalid date last calculated, and compare it to see if
        anything has changed before we trigger an expensive refresh.
        """
        d = self._get_invalid_date()
        if self.cached_date != d:
            log.debug("New invalid date selected, reloading screen.")
            self.cached_date = d
            self._reload_screen()
        else:
            log.debug("No change in invalid date, skipping screen reload.")

    def _get_invalid_date(self):
        """
        Returns a datetime object for the invalid date to use based on current
        state of the GUI controls.
        """
        if self.first_invalid_radiobutton.get_active():
            return make_today_now(self.last_valid_date)
        else:
            return self.date_picker.date

    def _load_last_valid_date(self):
        """
        Return a datetime object representing the day, month, and year of
        last validity. Ignore the timestamp returned from certlib.
        """
        d = find_first_invalid_date()
        return datetime(d.year, d.month, d.day, tzinfo=certificate.GMT())

    def _display_invalid(self):
        """
        Displays the list of products or entitlements that will invalid on
        the selected date.
        """
        sorter = CertSorter(self.product_dir, self.entitlement_dir,
                on_date=self._get_invalid_date())

        # These display the list of products invalid on the selected date:
        self.invalid_store.clear()

        # installed but not entitled products:
        na = _("N/A")
        for product_cert in sorter.unentitled_products.values():
            self.invalid_store.add_map({
                'active': False,
                'product_name': product_cert.getProduct().getName(),
                'contract': na,
                'end_date': na,
                'entitlement_id': None,
                'entitlement': None,
                'product_id': product_cert.getProduct().getHash(),
                'align': 0.0
            })

        # installed and invalid
        for product_id in sorter.expired_products.keys():
            ent_cert = sorter.expired_products[product_id]
            product = sorter.all_products[product_id].getProduct()
            self.invalid_store.add_map({
                'active': False,
                'product_name': product.getName(),
                'contract': ent_cert.getOrder().getNumber(),
                # is end_date when the cert expires or the orders end date? is it differnt?
                'end_date': '%s' % self.format_date(ent_cert.validRange().end()),
                'entitlement_id': ent_cert.serialNumber(),
                'entitlement': ent_cert,
                'product_id': product.getHash(),
                'align': 0.0
            })


    def _display_subscriptions(self):
        """
        Displays the list of subscriptions that will replace the selected
        products/entitlements that will be invalid.

        To do this, will will build a master list of all product IDs selected,
        both the top level marketing products and provided products. We then
        look for any subscription valid for the given date, which provides
        *any* of those product IDs. Note that there may be duplicate subscriptions
        shown. The user can select one subscription at a time to request an
        entitlement for, after which we will refresh the screen based on this new
        state.
        """
        self.subscriptions_store.clear()

        subscriptions_map = {}
        # this should be roughly correct for locally manager certs, needs
        # remote subs/pools as well

        # TODO: the above only hits entitlements, un-entitled products are not covered

        selected_products = self._get_selected_product_ids()
        pool_filter = managerlib.PoolFilter(self.product_dir, self.entitlement_dir)
        relevant_pools = pool_filter.filter_product_ids(
                self.pool_stash.compatible_pools.values(), selected_products)
        merged_pools = managerlib.merge_pools(relevant_pools).values()

        for entry in merged_pools:
            quantity = entry.quantity
            if quantity < 0:
                 available = _('unlimited')
            else:
                available = "%s of %s" % \
                    (available, quantity),
            self.subscriptions_store.add_map({
                'product_name': entry.product_name,
                'total_contracts': len(entry.pools),
                'total_subscriptions': entry.quantity,
                'available_subscriptions': available,
                'pool_id': entry.pools[0]['id'],
            })


    def _get_selected_product_ids(self):
        """
        Builds a master list of all product IDs for the selected invalid
        products/entitlements. In the case of entitlements which will be expired,
        we assume you want to keep all provided products you have now, so these
        provided product IDs will be included in the list.
        """
        all_product_ids = []
        for row in self.invalid_store:
            if row[self.invalid_store['active']]:
                ent_cert = row[self.invalid_store['entitlement']]
                if not ent_cert:
                    # This must be a completely unentitled product installed, just add it's
                    # top level product ID:
                    # TODO: can these product certs have provided products as well?
                    all_product_ids.append(row[self.invalid_store['product_id']])
                else:
                    for product in ent_cert.getProducts():
                        all_product_ids.append(product.getHash())
        log.debug("Calculated all selected invalid product IDs:")
        log.debug(all_product_ids)
        return all_product_ids

    def _on_invalid_active_toggled(self, cell, path):
        """
        Triggered whenever the user checks one of the products/entitlements
        in the invalid section of the UI.
        """
        treeiter = self.invalid_store.get_iter_from_string(path)
        item = self.invalid_store.get_value(treeiter, self.invalid_store['active'])
        self.invalid_store.set_value(treeiter, self.invalid_store['active'], not item)

        # refresh subscriptions
        self._display_subscriptions()

    def format_date(self, date):
        return managerlib.formatDate(date)

    def hide(self, widget, event, data=None):
        self.window.hide()
        return True

    def _update_sub_details(self, widget):
        """ Shows details for the current selected pool. """
        model, tree_iter = widget.get_selected()
        if tree_iter:
            product_name = model.get_value(tree_iter, self.subscriptions_store['product_name'])
            pool_id = model.get_value(tree_iter, self.subscriptions_store['pool_id'])
            provided = self.pool_stash.lookup_provided_products(pool_id)
            self.sub_details.show(product_name, products=provided)
            self.subscribe_button.set_sensitive(True)
        else:
            self.sub_details.clear()
            self.subscribe_button.set_sensitive(False)

    def subscribe_button_clicked(self, button):
        model, tree_iter = self.subscriptions_treeview.get_selection().get_selected()
        pool_id = model.get_value(tree_iter, self.subscriptions_store['pool_id'])

        pool = self.pool_stash.all_pools[pool_id]
        try:
            self.backend.uep.bindByEntitlementPool(self.consumer.uuid, pool['id'])
            managerlib.fetch_certificates(self.backend)
        except Exception, e:
            handle_gui_exception(e, _("Error getting subscription: %s"))

        self._reload_screen()