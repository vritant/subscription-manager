import sys

import logging
log = logging.getLogger('rhsm-app.' + __name__)

import pprint
pp = pprint.pprint


class GaImporter(object):
    def __init__(self):
        log.debug("ga_loader")
        print "ga_loader"
        self.ga_modules = ["GObject", "GLib", "Gdk", "Gtk", "Pango", "GdkPixbuf"]
        self.virtual_modules = {'subscription_manager.ga': ['subscription_manager.notga',
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
#            print "fullname: %s" % fullname
#            print "    path: %s" % path
#            print "fullname in self.virtual_modules"
            return self
        #if fullname == self.virtual_name:
        #    return self
        #print "   did not find the module: %s" % fullname
        return None

    def load_module(self, fullname):
        print "=== LOAD MODULE === load_module: fullname %s" % fullname
        #pp(sys.modules)
        if fullname in sys.modules:
            return sys.modules[fullname]

        if fullname not in self.virtual_modules:
            raise ImportError(fullname)

        real_module_name, real_fromlist = self.virtual_modules[fullname]
        print "real_module_name", real_module_name, real_fromlist

        if real_fromlist:
            ret = __import__(real_module_name, globals(), locals(), [real_fromlist])
#            print "from", getattr(ret, real_fromlist)
            pp(dir(ret))
            inner_ret = getattr(ret, real_fromlist)
            #pp(inner_ret)
            #pp(dir(inner_ret))
#            print inner_ret.__name__
            #inner_ret.__loader__
            #inner_ret.__name__ = fullname
            #inner_ret.__package__ = False
            ret = inner_ret

        else:
            ret = __import__(real_module_name)
            ret.__name__ = fullname
            ret.__loader__ = self
            ret.__file__ = ret.notga.ga_gtk3.__file__

            #print ret
            pp(dir(ret))
            for i in dir(ret):
                print "%s = %s" % (i, getattr(ret, i))

            #pp(sys.modules)
            sys.modules[fullname] = ret
            #pp(sys.modules)
            #sys.exit()

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
