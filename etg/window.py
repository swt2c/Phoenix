#---------------------------------------------------------------------------
# Name:        etg/window.py
# Author:      Robin Dunn
#
# Created:     27-Nov-2010
# Copyright:   (c) 2011 by Total Control Software
# License:     wxWindows License
#---------------------------------------------------------------------------

import etgtools
import etgtools.tweaker_tools as tools
from etgtools import ClassDef, MethodDef, ParamDef

PACKAGE   = "wx"   
MODULE    = "_core"
NAME      = "window"   # Base name of the file to generate to for this script
DOCSTRING = ""

# The classes and/or the basename of the Doxygen XML files to be processed by
# this script. 
ITEMS  = [ 'wxVisualAttributes',
           'wxWindow' ]    
    
OTHERDEPS = [ 'src/window_ex.cpp',   # some helper C++ code
              ]

#---------------------------------------------------------------------------

def run():
    # Parse the XML file(s) building a collection of Extractor objects
    module = etgtools.ModuleDef(PACKAGE, MODULE, NAME, DOCSTRING)
    etgtools.parseDoxyXML(module, ITEMS)
    
    #-----------------------------------------------------------------
    # Tweak the parsed meta objects in the module object as needed for
    # customizing the generated code and docstrings.    

    c = module.find('wxWindow')
    assert isinstance(c, etgtools.ClassDef)
    module.addGlobalStr('wxPanelNameStr', c)
        
    
    # First we need to let the wrapper generator know about wxWindowBase since
    # AddChild and RemoveChild need to use that type in order to be virtualized.
    winbase = ClassDef(name='wxWindowBase', bases=['wxEvtHandler'], abstract=True,
            items=[MethodDef(name='AddChild', isVirtual=True, type='void', protection='public',
                        items=[ParamDef(name='child', type='wxWindowBase*')]),
                   MethodDef(name='RemoveChild', isVirtual=True, type='void', protection='public',
                        items=[ParamDef(name='child', type='wxWindowBase*')])
                   ])
    module.insertItemBefore(c, winbase)
    
    # Now change the base class of wxWindow
    c.bases = ['wxWindowBase']
    
    # And fix the arg types we get from Doxy
    c.find('AddChild.child').type = 'wxWindowBase*'
    c.find('RemoveChild.child').type = 'wxWindowBase*'
    
    
    # We now return you to our regularly scheduled programming...
    c.includeCppCode('src/window_ex.cpp')

    # ignore some overloads that will be ambiguous afer wrapping
    c.find('GetChildren').overloads = []
    c.find('GetClientSize').findOverload('int *').ignore()
    c.find('GetSize').findOverload('int *').ignore()
    c.find('GetVirtualSize').findOverload('int *').ignore()
    c.find('GetPosition').findOverload('int *').ignore()
    c.find('GetScreenPosition').findOverload('int *').ignore()
    c.find('ClientToScreen').findOverload('int *').ignore()
    c.find('ScreenToClient').findOverload('int *').ignore()

    # Release the GIL for potentially blocking or long-running functions
    c.find('PopupMenu').releaseGIL()
    c.find('ProcessEvent').releaseGIL()
    c.find('ProcessWindowEvent').releaseGIL()
    c.find('ProcessWindowEventLocally').releaseGIL()
    
    # Add a couple wrapper functions for symmetry with the getters of the same name
    c.addPyMethod('SetRect', '(self, rect)', 'return self.SetSize(rect)')
    c.addPyProperty('Rect GetRect SetRect')
    c.addPyMethod('SetClientRect', '(self, rect)', 'return self.SetClientSize(rect)')
    c.addPyProperty('ClientRect GetClientRect SetClientRect')
                    
    m = c.find('GetTextExtent').findOverload('int *')
    m.pyName = 'GetFullTextExtent'
    m.find('w').out = True
    m.find('h').out = True
    m.find('descent').out = True
    m.find('externalLeading').out = True
    
    c.find('GetHandle').type = 'unsigned long'
    c.find('GetHandle').setCppCode("return wxPyGetWinHandle(self);")
    
    c.addCppMethod('void*', 'GetGtkWidget', '()', """\
    #ifdef __WXGTK__
        return (void*)self->GetHandle();
    #else
        return NULL;
    #endif
    """)
    
    c.addCppMethod('void', 'AssociateHandle', '(long handle)',
        doc="Associate the window with a new native handle",
        body="self->AssociateHandle((WXWidget)handle);")
    c.addCppMethod('void', 'DissociateHandle', '()',
        doc="Dissociate the current native handle from the window",
        body="self->DissociateHandle();")
        
    
    # Add some new methods
    c.addCppMethod('wxWindow*', 'GetTopLevelParent', '()',
                   'return wxGetTopLevelParent(self);',
                   briefDoc="Returns the first ancestor of this window which is a top-level window.")
    #c.addCppMethod('wxWindow*', 'FindWindowByLabel', '(const wxString& label)', 
    #               'return wxWindow::FindWindowByLabel(label, self);')
    
    c.addCppMethod('bool', 'MacIsWindowScrollbar', '(const wxWindow* sb)', """\
    #ifdef __WXMAC__
        return self->MacIsWindowScrollbar(sb); 
    #else
        return false;
    #endif
    """,
    pyArgsString="(sb)",
    briefDoc="Is the given widget one of this window's built-in scrollbars?  Only applicable on Mac.")

    
    c.addCppMethod('void', 'SetDimensions', '(int x, int y, int width, int height, int sizeFlags=wxSIZE_AUTO)', 
        pyArgsString="(x, y, width, height, sizeFlags=SIZE_AUTO)",
        body="""\
        self->SetSize(x, y, width, height, sizeFlags);
        """)
    c.addPyCode("Window.SetDimensions = wx.deprecated(Window.SetDimensions)")
    
    # Make the Register/UnregisterHotKey functions be available on Windows,
    # and empty stubs otherwise
    c.find('RegisterHotKey').setCppCode("""\
    #if wxUSE_HOTKEY
        return self->RegisterHotKey(hotkeyId, modifiers, virtualKeyCode);
    #else
        return false;
    #endif
    """)
    c.find('UnregisterHotKey').setCppCode("""\
    #if wxUSE_HOTKEY
        return self->UnregisterHotKey(hotkeyId);
    #else
        return false;
    #endif
    """)    
    c.find('RegisterHotKey').isVirtual = False
    c.find('UnregisterHotKey').isVirtual = False

    
    c.find('SetDoubleBuffered').setCppCode("""\
    #if defined(__WXGTK20__) || defined(__WXMSW__)
        self->SetDoubleBuffered(on);
    #endif
    """)

    c.addPyMethod('__nonzero__', '(self)',
        doc="Can be used to test if the C++ part of the window still exists, with \n"
            "code like this:\n\n"
            "    if theWindow:\n"
            "        doSomething()",
        body="""\
        import wx.siplib
        return not wx.siplib.isdeleted(self)
        """)
    
    # MSW only.  Do we want them wrapped?
    c.find('GetAccessible').ignore()
    c.find('SetAccessible').ignore()
    
    # Make some of the protected methods visible and overridable from Python
    c.find('SendDestroyEvent').ignore(False)

    c.find('Destroy').transferThis=True
    c.addPyMethod('PostCreate', '(self, pre)', 'pass', deprecated=True)
    
    # transfer ownership of these parameters to the C++ object
    c.find('SetCaret.caret').transfer = True
    c.find('SetToolTip.tip').transfer = True
    c.find('SetDropTarget.target').transfer = True
    c.find('SetConstraints.constraints').transfer = True
    c.find('SetSizer.sizer').transfer = True
    c.find('SetSizerAndFit.sizer').transfer = True
    
    # Define some properties using the getter and setter methods
    c.addProperty('AcceleratorTable GetAcceleratorTable SetAcceleratorTable')
    c.addProperty('AutoLayout GetAutoLayout SetAutoLayout')
    c.addProperty('BackgroundColour GetBackgroundColour SetBackgroundColour')
    c.addProperty('BackgroundStyle GetBackgroundStyle SetBackgroundStyle')
    c.addProperty('EffectiveMinSize GetEffectiveMinSize')
    c.addProperty('BestSize GetBestSize')
    c.addProperty('BestVirtualSize GetBestVirtualSize')
    c.addProperty('Border GetBorder')
    c.addProperty('Caret GetCaret SetCaret')
    c.addProperty('CharHeight GetCharHeight')
    c.addProperty('CharWidth GetCharWidth')
    c.addProperty('Children GetChildren')
    c.addProperty('ClientAreaOrigin GetClientAreaOrigin')
    c.addProperty('ClientSize GetClientSize SetClientSize')
    c.addProperty('Constraints GetConstraints SetConstraints')
    c.addProperty('ContainingSizer GetContainingSizer SetContainingSizer')
    c.addProperty('Cursor GetCursor SetCursor')
    c.addProperty('DefaultAttributes GetDefaultAttributes')
    c.addProperty('DropTarget GetDropTarget SetDropTarget')
    c.addProperty('EventHandler GetEventHandler SetEventHandler')
    c.addProperty('ExtraStyle GetExtraStyle SetExtraStyle')
    c.addProperty('Font GetFont SetFont')
    c.addProperty('ForegroundColour GetForegroundColour SetForegroundColour')
    c.addProperty('GrandParent GetGrandParent')
    c.addProperty('TopLevelParent GetTopLevelParent')
    c.addProperty('Handle GetHandle')
    c.addProperty('HelpText GetHelpText SetHelpText')
    c.addProperty('Id GetId SetId')
    c.addProperty('Label GetLabel SetLabel')
    c.addProperty('LayoutDirection GetLayoutDirection SetLayoutDirection')
    c.addProperty('MaxHeight GetMaxHeight')
    c.addProperty('MaxSize GetMaxSize SetMaxSize')
    c.addProperty('MaxWidth GetMaxWidth')
    c.addProperty('MinHeight GetMinHeight')
    c.addProperty('MinSize GetMinSize SetMinSize')
    c.addProperty('MinWidth GetMinWidth')
    c.addProperty('Name GetName SetName')
    c.addProperty('Parent GetParent')
    c.addProperty('Position GetPosition SetPosition')
    c.addProperty('ScreenPosition GetScreenPosition')
    c.addProperty('ScreenRect GetScreenRect')
    c.addProperty('Size GetSize SetSize')
    c.addProperty('Sizer GetSizer SetSizer')
    c.addProperty('ThemeEnabled GetThemeEnabled SetThemeEnabled')
    c.addProperty('ToolTip GetToolTip SetToolTip')
    c.addProperty('UpdateClientRect GetUpdateClientRect')
    c.addProperty('UpdateRegion GetUpdateRegion')
    c.addProperty('Validator GetValidator SetValidator')
    c.addProperty('VirtualSize GetVirtualSize SetVirtualSize')
    c.addProperty('WindowStyle GetWindowStyle SetWindowStyle')
    c.addProperty('WindowStyleFlag GetWindowStyleFlag SetWindowStyleFlag')
    c.addProperty('WindowVariant GetWindowVariant SetWindowVariant')
    c.addProperty('Shown IsShown Show')
    c.addProperty('Enabled IsEnabled Enable')
    c.addProperty('TopLevel IsTopLevel')
    c.addProperty('MinClientSize GetMinClientSize SetMinClientSize')
    c.addProperty('MaxClientSize GetMaxClientSize SetMaxClientSize')
    ##c.addProperty('GtkWidget GetGtkWidget')

    tools.fixWindowClass(c)

    # for compatibility with Classic
    c.addPyMethod('GetPositionTuple', '(self)', 'return self.GetPosition()', deprecated=True)
    c.addPyMethod('MoveXY',  '(self, x, y)', 'return self.Move(x, y)', deprecated=True)
    c.addPyMethod('SetSizeWH', '(self, w, h)', 'return self.SetSize(w,h)', deprecated=True)
    c.addPyMethod('SetVirtualSizeWH', '(self, w, h)', 'return self.SetVirtualSize(w,h)', deprecated=True)
    c.addPyMethod('GetVirtualSizeTuple', '(self)', 'return self.GetVirtualSize()', deprecated=True)
    c.addPyMethod('SetToolTipString',  '(self, string)', 'return self.SetToolTip(string)', deprecated=True)
    c.addPyMethod('ConvertDialogPointToPixels', '(self, point)', 'return self.ConvertDialogToPixels(point)', deprecated=True)
    c.addPyMethod('ConvertDialogSizeToPixels', '(self, size)', 'return self.ConvertDialogToPixels(point)', deprecated=True)

    #-----------------------------------------------------------------------
    # Other stuff
    
    module.addPyCode('''\
    class FrozenWindow(object):
        """
        A context manager to be used with Python 'with' statements
        that will freeze the given window for the duration of the
        with block.
        """
        def __init__(self, window):
            self._win = window
        def __enter__(self):
            self._win.Freeze()
            return self
        def __exit__(self, exc_type, exc_val, exc_tb):
            self._win.Thaw()
    ''')
    
    
    # Add a wrapper for wxWindowList and a new iterator class for it that
    # makes wxWindowList quack like a read-only Python sequence.
    module.addItem(tools.wxListWrapperTemplate('wxWindowList', 'wxWindow', module))
    
    module.addCppFunction('wxWindowList*', 'GetTopLevelWindows', '()', 
                          briefDoc="Returns a list-like object of the the application's top-level windows, (frames,dialogs, etc.)",
                          body="return &wxTopLevelWindows;")
    
    module.addPyCode("PyWindow = wx.deprecated(Window)")
    
    #-----------------------------------------------------------------
    tools.doCommonTweaks(module)
    tools.runGenerators(module)
    
    
    
#---------------------------------------------------------------------------
if __name__ == '__main__':
    run()

