#!/usr/bin/env python
# -*- coding: utf-8 -*-
#
# This file is part of the LibreOffice project.
#
# This Source Code Form is subject to the terms of the Mozilla Public
# License, v. 2.0. If a copy of the MPL was not distributed with this
# file, You can obtain one at http://mozilla.org/MPL/2.0/.
#

#This digs through a pile of bugzilla's and populates the cwd with a big
#collection of bug-docs in per-filetype dirs with bug-ids as names with
#prefixes to indicate which bug-tracker, e.g.
#
#fdo-bugid-X.suffix
#rhbz-bugid-X.suffix
#moz-bugid-X.suffix
#
#where X is the n'th attachment of that type in the bug

from __future__ import print_function
import feedparser
import base64
import datetime
import glob
import re
import os, os.path
import stat
import sys
import time
import xmlrpclib
import webbrowser
import subprocess
import zipfile
import mmap
try:
    from urllib.request import urlopen
except:
    from urllib import urlopen
try:
    import xmlrpc.client as xmlrpclib
except:
    import xmlrpclib
from xml.dom import minidom
from xml.sax.saxutils import escape

def urlopen_retry(url):
    maxretries = 3
    for i in range(maxretries + 1):
        try:
            return urlopen(url)
        except IOError as e:
            print("caught IOError: " + str(e))
            if maxretries == i:
                raise
            print("retrying...")

def already_parsed(attachmentid):
    if str(attachmentid) in open('parsedlog.txt').read():
        return 1
    return 0

def determine_attachment_mimetype(attachmentid):
    correctmimetype = subprocess.check_output("file --mime-type " + attachmentid, shell=True)
    #os.system('file --mime-type ' + attachmentid)
    correctmimetype = correctmimetype.rsplit(' ', 2)[1]
    #    print("correctmimetype: " + correctmimetype)
    return correctmimetype

def open_attachment_in_browser(attachmentid):
    attachmenturl = ("https://bugs.freedesktop.org/attachment.cgi?id=" + attachmentid + "&action=edit")
    webbrowser.open_new_tab(attachmenturl)
    input("Press Enter to continue...")

def get_from_bug_url_via_xml(url, mimetype):
    id = url.rsplit('=', 2)[1]
    print("parsing " + id)
    if id == '64672':
        return
    sock = urlopen_retry(url+"&ctype=xml")
    dom = minidom.parse(sock)
    sock.close()
    count = 0
    attachmentid = 0
    for attachment in dom.getElementsByTagName('attachment'):
        #print(" mimetype is", end=' ')
        for node in attachment.childNodes:
            if node.nodeName == 'attachid':
                attachmentid = node.firstChild.nodeValue
            
                if already_parsed(attachmentid):
                    print("we already did parse this bastard")
                    count += 1
                    break
        
            elif node.nodeName == 'type':
                #print(node.firstChild.nodeValue, end=' ')
                if node.firstChild.nodeValue.lower() != mimetype.lower():
                    print('skipping')
                    break
                count += 1
            elif node.nodeName == 'data':
                log = open('parsedlog.txt', 'a+')
                log.write(attachmentid + '\n')
                log.close()
                print('downloading ' + attachmentid)
                f = open(str(attachmentid), 'wb')
                f.write(base64.b64decode(node.firstChild.nodeValue))
                f.close()
                detectedmimetype = determine_attachment_mimetype(attachmentid).strip()
                if detectedmimetype == mimetype:
                    break
                breakit = 0
                for toignore in ignore:
                    if detectedmimetype == toignore:
                        print("Nops, we are not looking for this!!")
                        breakit = 1
                        break
                if (detectedmimetype == 'application/zip'):
                    print("potential ms-office doc detected! ")
                    zfile = zipfile.ZipFile("./" +attachmentid)
                    for item in zfile.namelist():
                        #print(item)
                        internaldir = item.rsplit('/', 1)[0]
                        #print(internaldir)
                        if internaldir == 'word':
                            detectedmimetype = 'application/vnd.openxmlformats-officedocument.wordprocessingml.document'
                            breakit = 0
                            break
                        elif internaldir == 'xl':
                            detectedmimetype = 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
                            breakit = 0
                            break
                        elif internaldir == 'ppt':
                            detectedmimetype = 'application/vnd.openxmlformats-officedocument.presentationml.presentation'
                            breakit = 0
                            break
                print(detectedmimetype)
                if (breakit == 0):
                    open_attachment_in_browser(attachmentid)
    return count

def get_through_rpc_query(url, mimetype):
    id = url.rsplit('=', 2)[1]
    print(id)
    query = dict()
    query['ids'] = id
    proxy = xmlrpclib.ServerProxy('https://bugs.freedesktop.org/xmlrpc.cgi')
    result = proxy.Bug.attachments(query)
    bugs = result['bugs'][id]
    count = 0
    #    import pprint
    #    pp = pprint.PrettyPrinter(indent=4)
    #    pp.pprint(bugs)
    
    for attachments in bugs:
        if attachments['content_type'] == mimetype:
            attachmentid = attachments['id']
            f = open(str(attachmentid), 'wb')
            f.write(attachments['data'])
            f.close()
            count += 1
    
    return count

def get_through_rss_query(queryurl, mimetype):
    url = queryurl + '?query_format=advanced&f1=attachments.mimetype&v1=' + mimetype +'&o1=equals&product=LibreOffice&ctype=atom'
    print('url is ' + url)
    d = feedparser.parse(url)
    print(str(len(d['entries'])) + ' bugs to process')
    attachCount = 0
    for entry in d['entries']:
        try:
            attachCount = attachCount + get_from_bug_url_via_xml(entry['id'], mimetype)
        except KeyboardInterrupt:
            raise # Ctrl+C should work
        except:
            print(entry['id'] + " failed: " + str(sys.exc_info()[0]))
            pass
        
        print("Total count = " + str(attachCount))
    
    #write it to a log
    file = open("mimetypecount.csv", "a")
    file.write("\"" + time.strftime("%d/%m/%Y") + "\",\"" + str(attachCount) + "\"\n")
    file.close()


rss_bugzilla = 'http://bugs.libreoffice.org/buglist.cgi'
mimetype = 'text/plain'
ignore = {'application/xml', 'text/x-c', 'text/x-java', 'text/html', 'summary', 'text/x-c++', 'text/x-diff', 'text/x-pascal', 'text/x-news', 'application/pgp-keys', 'application/vnd.ms-office', 'text/x-fortran'}

get_through_rss_query(rss_bugzilla, mimetype)

# vim:set shiftwidth=4 softtabstop=4 expandtab:
