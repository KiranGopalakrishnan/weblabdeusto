#!/usr/bin/python
# -*- coding: utf-8 -*-
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

import os
import sys
from optparse import OptionParser

COMMANDS = {
    'create'     : 'Create a new weblab instance', 
    'rebuild-db' : 'Rebuild the database of the weblab instance', 
    'start'      : 'Start an existing weblab instance', 
    'stop'       : 'Stop an existing weblab instance',
    'admin'      : 'Adminstrate a weblab instance',
    'monitor'    : 'Monitor the current use of a weblab instance',
}

def weblab():
    if len(sys.argv) in (1, 2) or sys.argv[1] not in COMMANDS:
        command_list = ""
        for command, help_text in COMMANDS.items():
            command_list += "\t%s\t\t%s\n" % (command, help_text)
        print >> sys.stderr, "Usage: %s option DIR [option arguments]\n\n%s\n" % (sys.argv[0], command_list)
        sys.exit(0)
    main_command = sys.argv[1]
    if main_command == 'create':
        weblab_create(sys.argv[2])
    else:
        print >>sys.stderr, "Command %s not yet implemented" % sys.argv[1]

COORDINATION_ENGINES = ['sql',   'redis'  ]
DATABASE_ENGINES     = ['mysql', 'sqlite' ]
SESSION_ENGINES      = ['sql',   'redis', 'memory']

def weblab_create(directory):
    parser = OptionParser(usage="%prog create DIR [options]")

    parser.add_option("--cores",                  dest="cores",           type="int",    default=1,
                                                  help = "Number of core servers.")

    parser.add_option("--start-port",             dest="start_ports",     type="int",    default=10000,
                                                  help = "From which port start counting.")

    parser.add_option("--db-engine",              dest="db_engine",       choices = DATABASE_ENGINES,
                                                  help = "Core database engine to use. Values: %s." % (', '.join(DATABASE_ENGINES)))


    parser.add_option("--db-name",                dest="db_name",         type="string", default="WebLabTests",
                                                  help = "Core database name.")

    parser.add_option("--db-user",                dest="db_user",         type="string", default="",
                                                  help = "Core database username.")

    parser.add_option("--db-passwd",              dest="db_passwd",       type="string", default="",
                                                  help = "Core database password.")

    parser.add_option("--coordination-engine",    dest="coord_engine",    choices = COORDINATION_ENGINES,
                                                  help = "Coordination engine used. Values: %s." % (', '.join(COORDINATION_ENGINES)))

    parser.add_option("--coordination-db-engine", dest="coord_db_engine", choices = DATABASE_ENGINES,
                                                  help = "Coordination database engine used, if the coordination is based on a database. Values: %s." % (', '.join(DATABASE_ENGINES)))

    parser.add_option("--coordination-db-name",   dest="coord_db_name",   type="string", default="WebLabCoordination",

                                                  help = "Coordination database name used, if the coordination is based on a database.")

    parser.add_option("--coordination-db-user",   dest="coord_db_user",   type="string", default="",
                                                  help = "Coordination database userused, if the coordination is based on a database.")

    parser.add_option("--coordination-db-passwd", dest="coord_db_passwd",   type="string", default="",
                                                  help = "Coordination database password used, if the coordination is based on a database.")

    parser.add_option("--coordination-redis-db",  dest="coord_redis_db",   type="int", default=0,
                                                  help = "Coordination redis DB used, if the coordination is based on redis.")


    parser.add_option("--session-storage",        dest="session_storage", choices = SESSION_ENGINES,
                                                  help = "Session storage used. Values: %s." % (', '.join(SESSION_ENGINES)) )

    parser.add_option("--inline-lab-server",      dest="inline_lab_serv", action="store_true", default=False,
                                                  help = "Laboratory server included in the same process as the core server. " 
                                                         "Only available if a single core is used." )

    parser.add_option("-f", "--force",            dest="force", action="store_true", default=False,
                                                   help = "Overwrite the contents even if the directory already existed.")

    (options, args) = parser.parse_args()

    if options.cores <= 0:
        print >> sys.stderr, "ERROR: There must be at least one core server."
        sys.exit(-1)

    if options.start_ports < 1 or options.start_ports >= 65535:
        print >> sys.stderr, "ERROR: starting port number must be at least 1"
        sys.exit(-1)

    if options.inline_lab_serv and options.cores > 1:
        print >> sys.stderr, "ERROR: Inline lab server is incompatible with more than one core servers. It would require the lab server, which does not make sense."
        sys.exit(-1)
        

    if os.path.exists(directory) and not options.force:
        print >> sys.stderr, "ERROR: Directory %s already exists. Use --force if you want to overwrite the contents." % directory
        sys.exit(-1)
    
    if os.path.exists(directory):
        if not os.path.isdir(directory):
            print >> sys.stderr, "ERROR: %s is not a directory. Delete it before proceeding." % directory
            sys.exit(-1)
    else:
        try:

            os.mkdir(directory)
        except Exception as e:
            print >> sys.stderr, "ERROR: Could not create directory %s: %s" % (directory, str(e))
            sys.exit(-1)

    open(os.path.join(directory, 'configuration.xml'), 'w').write("""<?xml version="1.0" encoding="UTF-8"?>""" 
    """<machines
        xmlns="http://www.weblab.deusto.es/configuration" 
        xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
        xsi:schemaLocation="global_configuration.xsd"
    >

    <machine>core_machine</machine>"""
    "\n\n</machines>\n")

    machine_dir = os.path.join(directory, 'core_machine')
    if not os.path.exists(machine_dir):
        os.mkdir(machine_dir)

    machine_configuration_xml = ("""<?xml version="1.0" encoding="UTF-8"?>"""
    """<instances
        xmlns="http://www.weblab.deusto.es/configuration" 
        xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
        xsi:schemaLocation="machine_configuration.xsd"
    >

    <configuration file="machine_config.py"/>

    """)
    for core_n in range(1, options.cores + 1):
        machine_configuration_xml += "<instance>core_server%s</instance>\n    " % core_n

    machine_configuration_xml += "\n</instances>\n"

    machine_config_py = ""

    open(os.path.join(machine_dir, 'configuration.xml'), 'w').write(machine_configuration_xml)
    open(os.path.join(machine_dir, 'machine_config.py'), 'w').write(machine_config_py)

    print options.cores, options.db_engine, options.inline_lab_serv
    
