# -*- coding: UTF-8 -*-
# *
# *  Copyright (C) 2012-2013 Garrett Brown
# *  Copyright (C) 2010      j48antialias
# *
# *  This Program is free software; you can redistribute it and/or modify
# *  it under the terms of the GNU General Public License as published by
# *  the Free Software Foundation; either version 2, or (at your option)
# *  any later version.
# *
# *  This Program is distributed in the hope that it will be useful,
# *  but WITHOUT ANY WARRANTY; without even the implied warranty of
# *  MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
# *  GNU General Public License for more details.
# *
# *  You should have received a copy of the GNU General Public License
# *  along with XBMC; see the file COPYING.  If not, write to
# *  the Free Software Foundation, 675 Mass Ave, Cambridge, MA 02139, USA.
# *  http://www.gnu.org/copyleft/gpl.html
# *
# *  Based on code by j48antialias:
# *  https://anarchintosh-projects.googlecode.com/files/addons_xml_generator.py

"""generator"""

import os
import sys
import re
import zipfile, shutil
from mako.template import Template

# Compatibility with 3.0, 3.1 and 3.2 not supporting u"" literals
if sys.version < '3':
    import codecs
    def u(x):
        return codecs.unicode_escape_decode(x)[0]
else:
    def u(x):
        return x

class GeneratorXML:
    """
        Generates a new addons.xml file from each addons addon.xml file
        and a new addons.xml.md5 hash file. Must be run from the root of
        the checked-out repo. Only handles single depth folder structure.
    """
    def __init__( self ):
        # generate files
        self._generate_addons_file()
        self._generate_md5_file()
        # notify user
        print("###Skończono aktualizację plików addons xml i md5###")

    def _generate_addons_file( self ):
        # addon list
        addons = os.listdir( "." )
        # final addons text
        addons_xml = u("<?xml version=\"1.0\" encoding=\"UTF-8\" standalone=\"yes\"?>\n<addons>\n")
        # loop thru and add each addons addon.xml file
        for addon in addons:
            try:
                # skip any file or .svn folder or .git folder
                if (not os.path.isdir(
                    addon) or ".svn" in addon or ".git" in addon or "zip" in addon or ".idea" in addon or "temp" in addon or "packages" in addon): continue
                # create path
                _path = os.path.join( addon, "addon.xml" )
                # split lines for stripping
                xml_lines = open( _path, "r" , encoding="utf8").read().splitlines()
                # new addon
                addon_xml = ""
                # loop thru cleaning each line
                for line in xml_lines:
                    # skip encoding format line
                    if ( line.find( "<?xml" ) >= 0 ): continue
                    # add line
                    if sys.version < '3':
                        addon_xml += unicode( line.rstrip() + "\n", "UTF-8" )
                    else:
                        addon_xml += line.rstrip() + "\n"
                # we succeeded so add to our final addons.xml text
                addons_xml += addon_xml.rstrip() + "\n\n"
                print(_path + " Udało się!")
            except Exception as e:
                # missing or poorly formatted addon.xml
                print(_path + " Fail!")
                print("Exception: %s\r\n" % e)
                continue
        # clean and add closing tag
        addons_xml = addons_xml.strip() + u("\n</addons>\n")
        # save file
        self._save_file( addons_xml.encode( "UTF-8" ), file="addons.xml" )

    def _generate_md5_file( self ):
        # create a new md5 hash
        try:
            import md5
            m = md5.new( open( "addons.xml", "r" , encoding="utf8").read() ).hexdigest()
        except ImportError:
            import hashlib
            m = hashlib.md5( open( "addons.xml", "r", encoding="UTF-8" ).read().encode( "UTF-8" ) ).hexdigest()

        # save file
        try:
            self._save_file( m.encode( "UTF-8" ), file="addons.xml.md5" )
        except Exception as e:
            # oops
            print("Wystąpił błąd poczas tworzenia pliku addons.xml.md5!\n%s" % e)

    def _save_file( self, data, file ):
        try:
            # write data to the file (use b for Python 3)
            open(file, "wb").write(data)
        except Exception as e:
            # oops
            print("Wystąpił błąd podczas zapisywania pliku %s !\n%s" % ( file, e ))

class GeneratorZIP:
    def __init__( self ):
        self._generate_zip_file()
        print("Skończono pakowanie")

    INDEX_TEMPLATE = r"""<!DOCTYPE HTML PUBLIC "-//W3C//DTD HTML 3.2 Final//EN">
    <html>
    <head>
     <title>Index of</title>
    </head>
    <body>
    <h1>${header}</h1>
    <table>
    % for name in names:
       % if '.zip' in name or '.md5' in name or '.xml' in name:
            <tr><td><a href="${name}">${name}</a></td></tr>
       % else:
            <tr><td><a href="${name}/">${name}</a></td></tr>
       % endif
    % endfor
    </table>
    </body>
    </html>
    """

    EXCLUDED = ['index.html', 'gitignore.ps1', 'Gemfile', 'Gemfile.lock', '.gitignore', '.gitlab-ci.yml', 'generator.py', '_config.yml', '.idea', '.git', 'pull.sh', 'pull2.sh', 'push.sh', '.gitmodules', '_config.yml']

    def index(self, dir):
        try:
            if dir == "":
                dir = os.getcwd()
            fnames = [fname for fname in sorted(os.listdir(dir))
                      if fname not in self.EXCLUDED]
            header = os.path.basename(dir)
            return(Template(self.INDEX_TEMPLATE).render(names=fnames, header=header))
        except:
            return

    def zipdir(self, path, ziph):
        # ziph is zipfile handle
        for root, dirs, files in os.walk(path):
            for file in files:
                ziph.write(os.path.join(root, file))

    def _generate_zip_file( self ):
        if not os.path.exists("zip"):
            os.makedirs("zip")
        folder = "zip"
# Pozostawienie starych wersji w katalogu
#       for the_file in os.listdir(folder):
#           file_path = os.path.join(folder, the_file)
#           try:
#               if os.path.isfile(file_path):
#                   os.unlink(file_path)
#               elif os.path.isdir(file_path): shutil.rmtree(file_path)
#           except Exception as e:
#                print(e)
#                continue
        addons = os.listdir( "." )
        for addon in addons:
            try:
                if (not os.path.isdir(
                    addon) or ".svn" in addon or ".git" in addon or "zip" in addon or ".idea" in addon or "temp" in addon or "packages" in addon): continue
                _path = os.path.join( addon, "addon.xml" )
                xml = open( _path, "r" , encoding="utf8").read()
                version = re.findall('''version=\"(.*?[0-9])\"''', xml)[1]
                addon_folder = "zip/" + addon
                if not os.path.exists(addon_folder):
                    os.makedirs(addon_folder)
                zipf = zipfile.ZipFile(addon_folder + "/" + addon + "-" + version + ".zip", 'w', zipfile.ZIP_DEFLATED)
                self.zipdir(addon, zipf)
                zipf.close()
                index = self.index(addon_folder)
                with open(addon_folder + '/index.html', 'w', encoding="utf8") as file:
                    file.write(index)
                print(_path.replace("/addon.xml","") + " Udało się!")
            except Exception as e:
                print("Exception: %s\r\n" % e)
                pass

        with open('index.html', 'w', encoding="utf8") as file:
            file.write(self.index(""))
        with open("zip" + '/index.html', 'w', encoding="utf8") as file:
            file.write(self.index("zip/"))

if ( __name__ == "__main__" ):
    for parent, dirnames, filenames in os.walk(os.path.dirname(sys.argv[0])):
        for fn in filenames:
            if fn.lower().endswith('.pyo') or fn.lower().endswith('.pyc'):
                print("Removing " + str(os.path.join(parent, fn)))
                os.remove(os.path.join(parent, fn))
    print("Tworzę pliki addons.xml i addons.md5")
    GeneratorXML()
    print("\r\nTworzę spakowane dodatki")
    GeneratorZIP()
