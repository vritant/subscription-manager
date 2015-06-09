import imp
import sys

import logging
log = logging.getLogger('rhsm-app.' + __name__)

import pprint
pp = pprint.pprint

class GaVirtualModule(object):
    pass


class GaImporter(object):
    def __init__(self):
        log.debug("ga_loader")
        print "ga_loader"
        self.ga_modules = ["GObject", "GLib", "Gdk", "Gtk", "Pango", "GdkPixbuf"]
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

    def find_module(self, fullname, path):
        #log.debug("find_module: fullname=%s", fullname)
        #log.debug("find_module: path=%s", path)
        if fullname in self.virtual_modules:
            print "fullname: %s" % fullname
            print "    path: %s" % path
#            print "fullname in self.virtual_modules"
            return self
        #if fullname == self.virtual_name:
        #    return self
        print "   did not find the module: %s" % fullname
        return None

    def _dirprint(self, module):
        print "module ", module, type(module)
        for i in dir(module):
            if i == "__builtins__":
                continue
            print "\t%s = %s" % (i, getattr(module, i))

    def load_module(self, fullname):
        print "load_module: fullname %s" % fullname
        #pp(sys.modules)
        if fullname in sys.modules:
            print "%s is in sys.modules" % fullname
            return sys.modules[fullname]

        if fullname not in self.virtual_modules:
            raise ImportError(fullname)

        real_module_name = real_fromlist = None
        mod_info = self.virtual_modules[fullname]
        if mod_info:
            real_module_name, real_fromlist = mod_info
        print "real_module_name", real_module_name, real_fromlist

        if real_fromlist:
            ret = __import__(real_module_name, globals(), locals(), [real_fromlist])
#            print "from", getattr(ret, real_fromlist)
            pp(dir(ret))
            self._dirprint(ret)
            inner_ret = getattr(ret, real_fromlist)
            print "inner"
            self._dirprint(inner_ret)
            #pp(inner_ret)
            #pp(dir(inner_ret))
#            print inner_ret.__name__
            #inner_ret.__loader__
            #inner_ret.__name__ = fullname
            #inner_ret.__package__ = False
            ret = inner_ret

        else:
            ret = sys.modules.setdefault(fullname, imp.new_module(fullname))
            ret.__name__ = fullname
            ret.__loader__ = self
            ret.__filename__ = fullname
            ret.__path__ = ['subscription_manager.ga']
            ret.__package__ = '.'.join(fullname.split('.')[:-1])
            self._dirprint(ret)

            ret.GTK_BUILDER_FILES_DIR = "/usr/share/rhsm/subscription_manager/gui/data/ui/"
            return ret
        #if real_fromname == "subscription_manager.ga":
        #    ret.__package__ = True

        ret.__name__ = fullname
        ret.__loader__ = self
        ret.__package__ = True
        sys.modules[fullname] = ret
#       pp(dir(ret))
        #pp(sys.modules)
        return ret

        raise ImportError(fullname)
