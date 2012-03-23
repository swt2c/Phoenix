#---------------------------------------------------------------------------
# Name:        etg/evtloop.py
# Author:      Robin Dunn
#
# Created:     22-Nov-2010
# Copyright:   (c) 2011 by Total Control Software
# License:     wxWindows License
#---------------------------------------------------------------------------

import etgtools
import etgtools.tweaker_tools as tools

PACKAGE   = "wx"   
MODULE    = "_core"
NAME      = "evtloop"   # Base name of the file to generate to for this script
DOCSTRING = ""

# The classes and/or the basename of the Doxygen XML files to be processed by
# this script. 
ITEMS  = [ 'wxEventLoopBase',
           'wxEventLoopActivator'
           ]    
    
#---------------------------------------------------------------------------

def run():
    # Parse the XML file(s) building a collection of Extractor objects
    module = etgtools.ModuleDef(PACKAGE, MODULE, NAME, DOCSTRING, 
                                check4unittest=False  # wxEventLoop is well tested in 
                                                      # myYield used by other tests...
                                )
    etgtools.parseDoxyXML(module, ITEMS)
    
    #-----------------------------------------------------------------
    # Tweak the parsed meta objects in the module object as needed for
    # customizing the generated code and docstrings.
    
    c = module.find('wxEventLoopBase')
    assert isinstance(c, etgtools.ClassDef)
    c.abstract = True

    c.find('Yield').releaseGIL()
    c.find('YieldFor').releaseGIL()
    
    
    c = module.find('wxEventLoopActivator')
    c.addPrivateAssignOp()
    c.addPrivateCopyCtor()
        
    #-----------------------------------------------------------------
    tools.doCommonTweaks(module)
    tools.runGenerators(module)
    
    
#---------------------------------------------------------------------------
if __name__ == '__main__':
    run()

