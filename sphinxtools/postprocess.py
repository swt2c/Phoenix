# -*- coding: utf-8 -*-
#!/usr/bin/env python

#---------------------------------------------------------------------------
# Name:        sphinxtools/postprocess.py
# Author:      Andrea Gavana
#
# Created:     30-Nov-2010
# Copyright:   (c) 2011 by Total Control Software
# License:     wxWindows License
#---------------------------------------------------------------------------

# Standard library imports
import os
import re
import cPickle
import glob
import random

# Phoenix-specific imports
import templates
from buildtools.config import copyIfNewer, writeIfChanged, newer

from utilities import Wx2Sphinx
from constants import HTML_REPLACE, SVN_REVISION, TODAY, SPHINXROOT, SECTIONS_EXCLUDE
from constants import CONSTANT_INSTANCES, WIDGETS_IMAGES_ROOT, SPHINX_IMAGES_ROOT


def MakeHeadings():
    """
    Generates the "headings.inc" file containing the substitution reference
    for the small icons used in the Sphinx titles, sub-titles and so on.

    The small icons are stored into the ``SPHINX_IMAGES_ROOT`` folder.    

    .. note:: The "headings.inc" file is created in the ``SPHINXROOT`` folder
       (see `sphinxtools/constants.py`).
    """

    images = glob.glob(SPHINX_IMAGES_ROOT + '/*.png')
    images.sort()
    
    heading_file = os.path.join(SPHINXROOT, 'headings.inc')

    text = ""
    for img in images:
        name = os.path.split(os.path.splitext(img)[0])[1]
        rel_path_index = img.find('_static')
        rel_path = img[rel_path_index:]

        width = ('overload' in name and [16] or [32])[0]
        text += templates.TEMPLATE_HEADINGS % (name, os.path.normpath(rel_path), width)

    writeIfChanged(heading_file, text)    

# ----------------------------------------------------------------------- #

def SphinxIndexes(sphinxDir):
    """
    This is the main function called after the `etg` process has finished.

    It class other functions to generate the standalone functions page, the
    main class index and some clean-up/maintenance of the generated ReST
    files.
    """

    pklfiles = glob.glob(sphinxDir + '/*.pkl')
    
    for file in pklfiles:
        if file.endswith('functions.pkl'):
            ReformatFunctions(file)
        elif 'classindex' in file:
            MakeClassIndex(file)

    BuildEnumsAndMethods(sphinxDir)


# ----------------------------------------------------------------------- #

def BuildEnumsAndMethods(sphinxDir):
    """
    This function does some clean-up/refactoring of the generated ReST files by:

    1. Removing the `:meth:` reference to Enums, as they are not methods, and replacing
       it with the `:ref:` role. This information is unfortunately not known when the
       main `etgtools/sphinx_generator.py` runs.
    2. Removing the "Perl note" stuff from the text (and we should clean up the
       wxWidgets docs at the source to remove the wxPython notes as well).
    3. Substituting the `:ref:` role for unreferenced classes (these may be classes yet
       to be ported to Phoenix or C++-specific classes which will never be ported to
       Phoenix) with simple backticks.
    4. Some cleanup.
    """

    fid = open(os.path.join(sphinxDir, 'class_summary.lst'), 'rb')
    class_summary = cPickle.load(fid)
    fid.close()

    unreferenced_classes = {}
    
    textfiles = glob.glob(sphinxDir + '/*.txt')
    enum_files = glob.glob(sphinxDir + '/*.enumeration.txt')

    enum_base = [os.path.split(os.path.splitext(enum)[0])[1] for enum in enum_files]
    enum_base = [enum.replace('.enumeration', '') for enum in enum_base]

    enum_dict = {}

    for enum in enum_base:
        enum_dict[':meth:`%s`'%enum] = ':ref:`%s`'%enum
    
    for input in textfiles:
                
        fid = open(input, 'rt')
        orig_text = text = fid.read()
        fid.close()

        for old, new in enum_dict.items():
            text = text.replace(old, new)

        widget_name = os.path.split(os.path.splitext(input)[0])[1]

        if widget_name in SECTIONS_EXCLUDE:
            start, end = SECTIONS_EXCLUDE[widget_name]
            lindex = text.index(start)
            rindex = text.index(end)
            text = text[0:lindex] + text[rindex:]
            
        # Replace the "Perl Note" stuff, we don't need it
        newtext = ''
        for line in text.splitlines():
            if 'perl note' in line.lower():
                continue
            newtext += line + '\n'

        text = newtext
    
        text = FindInherited(input, class_summary, enum_base, text)
        text, unreferenced_classes = RemoveUnreferenced(input, class_summary, enum_base, unreferenced_classes, text)
        
        text = text.replace('wx``', '``')
        text = text.replace('wx.``', '``')
        text = text.replace('non-NULL', 'not ``None``')
        text = text.replace(',,', ',').replace(', ,', ',')

        if 'DocstringsGuidelines' not in input:
            # Leave the DocstringsGuidelines.txt file alone on these ones
            text = text.replace(':note:', '.. note::')            
            text = text.replace(':see:', '.. seealso::')
            
        text = text.replace('`String`&', 'string')
        text = text.replace('See also\n', '.. seealso:: ')
        # Avoid Sphinx warnings on wx.TreeCtrl
        text = text.replace('**( `', '** ( `')
        # Replace EmptyString stuff
        text = text.replace('EmptyString', "''")
        # Replace ArrayString stuff...
        text = text.replace('ArrayString()', '[]')
        text = text.replace('ArrayString', 'list of strings')
        
        if text != orig_text:
            fid = open(input, 'wt')
            fid.write(text)
            fid.close()

    if not unreferenced_classes:
        return

    warn = '\n\nWARNING: there are %d instances of referenced classes/enums, via the `:ref:` role, which\n' \
           'are not in the list of available classes (these may be classes yet to be ported to Phoenix\n' \
           'or C++-specific classes which will never be ported to Phoenix).\n\n' \
           '*sphinxgenerator* has replaced the `:ref:` role for them with simple backticks, i.e.:\n\n' \
           '    :ref:`MissingClass` ==> `MissingClass`\n\n' \
           'to avoid warning from Sphinx and Docutils, and saved a list of their occurrences into\n' \
           'the text file "unreferenced_classes.inc" together with the ReST file names where they\n' \
           'appear.\n\n'

    keys = unreferenced_classes.keys()
    keys.sort()

    fid = open(os.path.join(SPHINXROOT, 'unreferenced_classes.inc'), 'wt')
    fid.write('\n')
    fid.write('='*50 + ' ' + '='*50 + '\n')
    fid.write('%-50s %-50s\n'%('Reference', 'File Name(s)'))
    fid.write('='*50 + ' ' + '='*50 + '\n')
              
    for key in keys:
        fid.write('%-50s %-50s\n'%(key, ', '.join(unreferenced_classes[key])))

    fid.write('='*50 + ' ' + '='*50 + '\n')
    fid.close()

    print warn%(len(keys))
            

# ----------------------------------------------------------------------- #

def FindInherited(input, class_summary, enum_base, text):

    # Malformed inter-links
    regex = re.findall(r'\S:meth:\S+', text)
    for regs in regex:
        newreg = regs[0] + ' ' + regs[1:]
        text = text.replace(regs, newreg)

    regex = re.findall(r':meth:\S+', text)

    for regs in regex:
        
        hasdot = '.' in regs
        hastilde = '~' in regs

        if regs.count('`') < 2:
            continue
        
        full_name = regs[regs.index('`')+1:regs.rindex('`')]
        full_name = full_name.replace('~', '')

        curr_class = dummy = os.path.split(os.path.splitext(input)[0])[1]
        
        if hasdot:
            newstr = full_name.split('.')
            curr_class, meth_name = '.'.join(newstr[0:-1]), newstr[-1]
        else:
            meth_name = full_name
        
        if meth_name == curr_class:
            newtext = ':ref:`%s`'%meth_name
            text = text.replace(regs, newtext, 1)
            continue


##        elif meth_name in enum_base:
##            newtext = ':ref:`%s`'%meth_name
##            text = text.replace(regs, newtext, 1)
##            continue
                        

        if meth_name in CONSTANT_INSTANCES:
            text = text.replace(regs, '``%s``'%meth_name, 1)
            continue
            
        if curr_class not in class_summary:
            continue
        
        methods, bases = class_summary[curr_class]

        if meth_name in methods:
            continue

        newstr = ''

        for cls in bases:
            if cls not in class_summary:
                continue

            submethods, subbases = class_summary[cls]

            if meth_name in submethods:
                if not hasdot:
                    newstr = ':meth:`~%s.%s`'%(cls, meth_name)                        
                elif not hastilde:
                    newstr = ':meth:`%s.%s`'%(cls, meth_name)
                elif hasdot:
                    newstr = ':meth:`~%s.%s`'%(cls, meth_name)
                else:
                    newstr = ':meth:`%s.%s`'%(cls, meth_name)

                break                        

        if newstr:
            text = text.replace(regs, newstr, 1)

    return text            


# ----------------------------------------------------------------------- #

def RemoveUnreferenced(input, class_summary, enum_base, unreferenced_classes, text):

    regex = re.findall(':ref:`(.*?)`', text)
    
    for reg in regex:
        if reg in class_summary or reg in enum_base:
            continue

        if ' ' in reg or '-' in reg:
            # Leave the items with spaces/dash alone, as they are
            # Overview pages
            continue

        if reg not in unreferenced_classes:
            unreferenced_classes[reg] = []

        split = os.path.split(input)[1]
        if split not in unreferenced_classes[reg]:
            unreferenced_classes[reg].append(split)
            
        text = text.replace(':ref:`%s`'%reg, '`%s`'%reg, 1)

    return text, unreferenced_classes        


# ----------------------------------------------------------------------- #

def ReformatFunctions(file):

    text_file = os.path.splitext(file)[0] + '.txt'
    local_file = os.path.split(file)[1]
    
    if not newer(file, text_file):
        return
    
    fid = open(file, 'rb')
    functions = cPickle.load(fid)
    fid.close()
    
    if local_file.count('.') == 1:
        # Core functions
        label = 'Core'
    else:
        label = local_file.split('.')[0:-2][0]

    names = functions.keys()
    names = [name.lower() for name in names]
    names.sort()

    text = templates.TEMPLATE_FUNCTION_SUMMARY % (label, label)

    letters = []
    for fun in names:
        upper = fun[0].upper()
        if upper not in letters:
            letters.append(upper)

    text += '  |  '.join([':ref:`%s <%s %s>`'%(letter, label, letter) for letter in letters])
    text += '\n\n\n'

    names = functions.keys()
    names = sorted(names, key=str.lower)

    for letter in letters:
        text += '.. _%s %s:\n\n%s\n^\n\n'%(label, letter, letter)
        for fun in names:
            if fun[0].upper() != letter:
                continue

            text += '* :func:`%s`\n'%fun

        text += '\n\n'

    text += 'Functions\n=============\n\n'

    for fun in names:
        text += functions[fun] + '\n'
    
    writeIfChanged(text_file, text)

# ----------------------------------------------------------------------- #

def MakeClassIndex(file):

    text_file = os.path.splitext(file)[0] + '.txt'
    local_file = os.path.split(file)[1]

    if not newer(file, text_file):
        return
    
    fid = open(file, 'rb')
    classes = cPickle.load(fid)
    fid.close()
    
    if local_file.count('.') == 1:
        # Core functions
        label = 'Core'
    else:
        label = local_file.split('.')[0:-2][0]

    names = classes.keys()
    names.sort()

    text = templates.TEMPLATE_CLASS_INDEX % (label, label)

    text += 80*'=' + ' ' + 80*'=' + '\n'
    text += '%-80s **Short Description**\n'%'**Class**'
    text += 80*'=' + ' ' + 80*'=' + '\n'

    for cls in names:
        text += '%-80s %s\n'%(':ref:`%s`'%Wx2Sphinx(cls)[1], classes[cls])

    text += 80*'=' + ' ' + 80*'=' + '\n'

    writeIfChanged(text_file, text)


# ----------------------------------------------------------------------- #

def GenGallery():

    link = '<div class="gallery_class">'

    link_template = """\
    <table><caption align="bottom"><a href="%s"<b>%s</b></a</caption>
    <tr>
    <td><a href="%s"><img src="_static/images/widgets/fullsize/%s/%s" border="20" alt="%s"/></a>
    </td>
    </tr>
    </table>
    """

    image_folder = WIDGETS_IMAGES_ROOT
    platforms = ['wxmsw', 'wxgtk', 'wxmac']

    image_files = {}

    pwd = os.getcwd()

    for folder in platforms:
        plat_folder = os.path.join(image_folder, folder)
        os.chdir(plat_folder)
        
        image_files[folder] = glob.glob('*.png')

    os.chdir(pwd)

    txt_files = glob.glob(SPHINXROOT + '/*.txt')
    html_files = {}

    for text in txt_files:
        simple = os.path.split(os.path.splitext(text)[0])[1]
        possible = simple.split('.')[-1]
        possible = possible.lower()
        html_files[possible + '.png'] = simple + '.html'

    keys = html_files.keys()
    keys.sort()

    text = ''
    
    for key in keys:
        possible_png = key
        html = html_files[possible_png]

        rand_list = range(3)
        random.shuffle(rand_list)

        for plat_index in rand_list:
            platform = platforms[plat_index]
            plat_images = image_files[platform]

            if possible_png in plat_images:
                text += link_template%(html, os.path.splitext(html)[0], html, platform, possible_png, os.path.splitext(html)[0])
                text += '\n'
                break

    gallery = os.path.join(SPHINXROOT, '_templates', 'gallery.html')
    writeIfChanged(gallery, templates.TEMPLATE_GALLERY % text)
        

# ----------------------------------------------------------------------- #

def AddPrettyTable(text):
    """ Unused at the moment. """

    newtext = """<br>
<table border="1" class="docutils"> """
    newtext2 = """<br>
<table border="1" class="last docutils"> """

    text = text.replace('<table border="1" class="docutils">', newtext)
    text = text.replace('<table border="1" class="last docutils">', newtext2)

    othertext = """class="pretty-table">"""

    text = text.replace('class="docutils">', othertext)
    text = text.replace('class="last docutils">', othertext)
    
    return text


# ----------------------------------------------------------------------- #

def ClassToFile(line):

    if '&#8211' not in line:
        return line
    
    if 'href' in line and '<li>' in line and '(' in line and ')' in line:        
        indx1 = line.index('href=')
        if 'title=' in line:
            indx2 = line.rindex('title=')
            paramdesc = line[indx1+6:indx2-2]
            
            if '.html#' in paramdesc:
                newparamdesc = paramdesc[:]
                lower = paramdesc.index('#') + 1

                letter = paramdesc[lower]
                if letter.isupper():
                    newparamdesc = newparamdesc[0:lower] + letter.lower() + newparamdesc[lower+1:]
                    newparamdesc = newparamdesc.replace(letter, letter.lower(), 1)
                    line = line.replace(paramdesc, newparamdesc)

    return line


# ----------------------------------------------------------------------- #

def PostProcess(folder):

    fileNames = glob.glob(folder + "/*.html")

    phoenix_image = '<div class="floatcenter" style="background-color: white; text-align: middle; align: middle; padding: 40px 10px 15px 15px">\n' \
                    '<img src="_static/images/sphinxdocs/phoenix_top.png" alt="Phoenix Logo" align="middle" />\n' \
                    '</div>'


    enum_files = glob.glob(folder + '/*.enumeration.html')

    enum_base = [os.path.split(os.path.splitext(enum)[0])[1] for enum in enum_files]
    enum_base = [enum.replace('.enumeration', '') for enum in enum_base]

    enum_dict = {}
    # ENUMS

    for indx, enum in enumerate(enum_base):
        html_file = os.path.split(enum_files[indx])[1]
        base = enum.split('.')[-1]        
        new = '(<a class="reference internal" href="%s" title="%s"><em>%s</em></a>)'%(html_file, base, base)
        enum_dict['(<em>%s</em>)'%enum] = new

    for files in fileNames:

        if "genindex" in files or "modindex" in files:
            continue

        methods_done = properties_done = False
        
        fid = open(files, "rt")
        orig_text = text = fid.read()
        fid.close()

        text = text.replace('|SVN|', SVN_REVISION)
        text = text.replace('|TODAY|', TODAY)

        split = os.path.split(files)[1]
        
        if split not in ['index.html', 'main.html']:
            text = text.replace(phoenix_image, '')
        
##        text = AddPrettyTable(text)
        text = text.replace('&#8211; <p>', '&#8211; ')
        text = text.replace('<p><img alt="overload"', '<br><p><img alt="overload"')
        text = text.replace('<strong>Overloaded Implementations</strong>', '<em><strong>Overloaded Implementations</strong></em>')
        text = text.replace('<strong>~~~</strong></p>', '<hr style="color:#0000FF;background-color:#0000FF;height:1px;border:none;width:50%;float:left" /></p><br>')
        
        for item in HTML_REPLACE:
            text = text.replace('<dl class="%s">'%item, '<br><hr />\n<dl class="%s">'%item)

        newtext = ''
        splitted_text = text.splitlines()
        len_split = len(splitted_text)
        
        for index, line in enumerate(splitted_text):
            if '<div class="admonition-availability admonition' in line:
                line = '<div class="admonition-availability admonition availability">'
                
##            line = ClassToFile(line)

            if index < len_split - 1:

                if line.strip() == '<br><hr />':
                    
                    next_line = splitted_text[index+1]
                    stripline = next_line.strip()
                    
                    if (stripline == '<dl class="staticmethod">' or stripline == '<dl class="method">') and not methods_done:
                        line = '<br><h3>Methods<a class="headerlink" href="#methods" title="Permalink to this headline">¶</a></h3>' + '\n' + line
                        methods_done = True
                        
                    elif stripline == '<dl class="attribute">' and not properties_done:
                        line = '<br><h3>Properties<a class="headerlink" href="#properties" title="Permalink to this headline">¶</a></h3>' + '\n' + line
                        properties_done = True
                
            newtext += line + '\n'                

        for old, new in enum_dict.items():
            newtext = newtext.replace(old, new)

        if orig_text != newtext:
            fid = open(files, "wt")
            fid.write(newtext)
            fid.close()


# ----------------------------------------------------------------------- #

