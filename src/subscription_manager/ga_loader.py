import imp
import sys

import logging
log = logging.getLogger('rhsm-app.' + __name__)

import pprint
pp = pprint.pprint


class GaImporter(object):
    namespace = "subscription_manager.ga"
    virtual_modules = {}

    def find_module(self, fullname, path):
        if fullname in self.virtual_modules:
            return self
        return None

    def load_module(self, fullname):
        print "load_module: fullname %s" % fullname
        if fullname in sys.modules:
            return sys.modules[fullname]

        if fullname not in self.virtual_modules:
            raise ImportError(fullname)

        # The base namespace
        if fullname == self.namespace:
            return self._namespace_module()

        real_module_name = real_module_from = None
        mod_info = self.virtual_modules[fullname]
        print mod_info
        if mod_info:
            real_module_name, real_module_from = mod_info

        if not real_module_from:
            raise ImportError(fullname)

        # looks like a real_module alias
        return self._import_real_module(fullname, real_module_name, real_module_from)

    def _import_real_module(self, fullname, module_name, module_from):
        print "module_from", module_from
        ret = __import__(module_name, globals(), locals(), [module_from])
        inner_ret = getattr(ret, module_from)
        ret = inner_ret
        ret.__name__ = fullname
        ret.__loader__ = self
        ret.__package__ = True
        sys.modules[fullname] = ret
        return ret

    def _new_module(self, fullname):
        """Create a an empty module, we can populate with impl specific."""
        ret = sys.modules.setdefault(fullname, imp.new_module(fullname))
        ret.__name__ = fullname
        ret.__loader__ = self
        ret.__filename__ = fullname
        ret.__path__ = [fullname]
        ret.__package__ = '.'.join(fullname.split('.')[:-1])
        pp(dir(ret))
        return ret

    def _namespace_module(self):
        return self._new_module(self.namespace)

    def _dirprint(self, module):
        return
        print "module ", module, type(module)
        for i in dir(module):
            if i == "__builtins__":
                continue
            print "\t%s = %s" % (i, getattr(module, i))


class GaImporterGtk3(GaImporter):

    def __init__(self):
        log.debug("ga_loader")
        self.virtual_modules = {'subscription_manager.ga': None,
                                'subscription_manager.ga.info': ['subscription_manager.notga',
                                                                 'ga_gtk3'],
                                'subscription_manager.ga.GObject': ['gi.repository',
                                                                    'GObject'],
                                'subscription_manager.ga.Gdk': ['gi.repository',
                                                                'Gdk'],
                                'subscription_manager.ga.Gtk': ['gi.repository',
                                                                'Gtk'],
                                'subscription_manager.ga.GLib': ['gi.repository',
                                                                 'GLib'],
                                'subscription_manager.ga.GdkPixbuf': ['gi.repository',
                                                                      'GdkPixbuf'],
                                'subscription_manager.ga.Pango': ['gi.repository',
                                                                  'Pango']}


def init_ga():
    gtk_version = 3
    if gtk_version == 3:
        sys.meta_path.append(GaImporterGtk3())
    if gtk_version == 2:
        raise Exception('That does not work yet')
