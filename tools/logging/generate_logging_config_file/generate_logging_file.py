#!/usr/bin/env python
#-*-*- encoding: utf-8 -*-*-
#
# Copyright (C) 2005 onwards University of Deusto
# All rights reserved.
#
# This software is licensed as described in the file COPYING, which
# you should have received as part of this distribution.
#
# This software consists of contributions made by many individuals, 
# listed below:
#
# Author: Pablo Orduña <pablo@ordunya.com>
# 

import time
import sys
import logging
import logging.config
import StringIO

HEADER = """#
# logging module file generated by generate_logging_file
# at %s. 
# 
# You should change the script configuration instead of
# this file directly.
# 

""" % time.asctime()

class Generator(object):
    def __init__(self, modules, prefix, suffix, max_file_size, max_handler_size, check = False):
        super(Generator, self).__init__()
        self._modules          = modules
        self._prefix           = prefix
        self._suffix           = suffix
        self._max_file_size    = max_file_size
        self._max_handler_size = max_handler_size
        self._backup_count     = max_handler_size / max_file_size
        self._check            = check

        invalid_levels = filter( 
                    lambda x : not hasattr(logging,x[0]), 
                    modules.values() 
                )
        if len(invalid_levels) > 0:
            raise "%s invalid levels found: %s" % (len(invalid_levels),invalid_levels)

    def generate_header(self):
        text  = "# \n"
        text += "# logging module file generated by %s\n" % __file__
        text += "# at %s.\n" % time.asctime()
        text += "# \n"
        text += "# You should change the script configuration instead of\n"
        text += "# this file directly.\n"
        text += "# \n"
        text += "# Call it like: \n"
        text += "#   Generator( \n"
        text += "#       { \n"
        for module in self._modules:
            text += "#          %s : %s\n" % (repr(module), repr(self._modules[module]))
        text += "#       } \n"
        text += "#       %s, \n" % self._prefix
        text += "#       %s, \n" % self._suffix
        text += "#       %s, \n" % self._max_file_size
        text += "#       %s, \n" % self._max_handler_size
        text += "#       %s  \n" % self._check
        text += "#   )\n"
        text += "# \n"
        return text + "\n"

    def generate_loggers_header(self):
        text  = "[loggers]\n"
        text += "keys=root,"
        for module in self._modules:
            text += module.replace('.','_') + ","
        return text[:-1] + "\n\n"

    def generate_handlers_header(self):
        text  = "[handlers]\n"
        text += "keys=root_handler,"
        for module in self._modules:
            level, make_handler = self._modules[module]
            if make_handler:
                text += module.replace('.','_') + '_handler,'
        return text[:-1] + "\n\n"

    def generate_formatters_header(self):
        text  = "[formatters]\n"
        text += "keys=simpleFormatter"
        return text + "\n\n"

    def generate_loggers(self):
        tree = self.build_tree()

        text  = "[logger_root]\n"
        text += "level=NOTSET\n"
        text += "handlers=root_handler\n"
        text += "propagate=0\n"
        text += "parent=\n"
        text += "channel=\n"
        text += "\n"

        def get_dict(tree, nodes):
            cur_dict = tree
            for node in nodes:
                cur_dict = cur_dict[node]
            return cur_dict

        def parse_tree(tree, nodes, latest_handler):
            dottedname = '.'.join(nodes)
            linedname  = '_'.join(nodes)

            text = ""
            if self._modules.has_key(dottedname):
                level, make_handler = self._modules[dottedname]
                if make_handler:
                    latest_handler = "%s_handler" % linedname
                text += "[logger_%s]\n" % linedname
                text += "level=%s\n" % level
                text += "handlers=%s\n" % latest_handler
                text += "qualname=%s\n" % dottedname
                text += "propagate=%s\n" % ( make_handler and '0' or '1' )
                text += "parent=%s\n" % ( '_'.join(nodes[:-1]) or 'root' )
                text += "channel=%s\n" % linedname
                text += "\n"

            for new_node in get_dict(tree, nodes).keys():
                text += parse_tree(tree, nodes + (new_node,), latest_handler)

            return text

        text += parse_tree(tree, (), 'root_handler')

        return text

    def generate_handlers(self):
        text = "[handler_root_handler]\n"
        text += "class=handlers.RotatingFileHandler\n"
        text += "formatter=simpleFormatter\n"
        text += "args=('%s_root_%s','a',%s,%s)\n" % (self._prefix, self._suffix, self._max_file_size, self._backup_count)
        text += "\n"

        for module in self._modules:
            _, make_handler = self._modules[module]
            if make_handler:
                text += "[handler_%s_handler]\n" % module.replace('.','_')
                text += "class=handlers.RotatingFileHandler\n"
                text += "formatter=simpleFormatter\n"
                text += "args=('%s_%s_%s','a',%s,%s)\n" % (self._prefix, module.replace('.','_'), self._suffix, self._max_file_size, self._backup_count)
                text += "\n"
        return text

    def generate_formatter(self):
        text  = "[formatter_simpleFormatter]\n"
        text += "format=%(asctime)s - %(name)s - %(levelname)s - %(message)s\n"
        text += "datefmt=\n"
        text += "class=logging.Formatter\n"
        return text + "\n"


    def generate_all(self):
        text = (
            self.generate_header()            +
            self.generate_loggers_header()    +
            self.generate_handlers_header()   + 
            self.generate_formatters_header() +
            self.generate_loggers()           +
            self.generate_handlers()          +
            self.generate_formatter()
        )

        if self._check:
            try:
                f = StringIO.StringIO(text)
                logging.config.fileConfig(f)
            except Exception, e:
                print >>sys.stderr,"The generated file will not work: %s" % e
            
        return text

    def build_tree(self):
        tree = {}
        for module in self._modules:
            submodules = module.split('.')

            remaining = submodules
            parsed    = []
            cur_dir   = tree

            for submodule in submodules:
                if cur_dir.has_key(submodule):
                    cur_dir = cur_dir[submodule]
                else:
                    cur_dir[submodule] = {}
                    cur_dir = cur_dir[submodule]
        return tree

if __name__ == '__main__':
    import configuration as cfg

    generator = Generator( cfg.MODULES, cfg.PREFIX, cfg.SUFFIX,
                cfg.MAX_FILE_SIZE, cfg.MAX_HANDLER_SIZE )
    print generator.generate_all()
