# encoding: UTF-8
# This file is part of pygubu.

#
# Copyright 2012-2013 Alejandro Autalán
#
# This program is free software: you can redistribute it and/or modify it
# under the terms of the GNU General Public License version 3, as published
# by the Free Software Foundation.
#
# This program is distributed in the hope that it will be useful, but
# WITHOUT ANY WARRANTY; without even the implied warranties of
# MERCHANTABILITY, SATISFACTORY QUALITY, or FITNESS FOR A PARTICULAR
# PURPOSE.  See the GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License along
# with this program.  If not, see <http://www.gnu.org/licenses/>.
#
# For further info, check  http://pygubu.web.here

from __future__ import unicode_literals
from __future__ import print_function
import platform
import os
import sys
import logging
import webbrowser
import importlib
import argparse

try:
    import tkinter as tk
    from tkinter import ttk
    from tkinter import filedialog
    from tkinter import messagebox
except:
    import Tkinter as tk
    import ttk
    import tkMessageBox as messagebox
    import tkFileDialog as filedialog


import pygubu
from pygubu import builder
from pygubu.stockimage import StockImage, StockImageException
from . import util
from .uitreeeditor import WidgetsTreeEditor
from .previewer import PreviewHelper
from .i18n import translator
from pygubu.widgets.accordionframe import AccordionFrame
from pygubu.widgets.autoarrangeframe import AutoArrangeFrame
from pygubu.widgets.scrollbarhelper import ScrollbarHelper
import pygubu.widgets.simpletooltip as tooltip
import pygubudesigner
from pygubudesigner.preferences import PreferencesUI, get_custom_widgets, get_option
from pygubudesigner.scriptgenerator import ScriptGenerator


#Initialize logger
logger = logging.getLogger(__name__)

#translator function
_ = translator

def init_pygubu_widgets():
    import pkgutil
    #initialize standard ttk widgets
    import pygubu.builder.ttkstdwidgets

    #initialize extra widgets
    widgets_pkg = 'pygubu.builder.widgets'
    mwidgets = importlib.import_module(widgets_pkg)

    for _, modulename, _ in pkgutil.iter_modules(mwidgets.__path__, mwidgets.__name__ + "."):
        try:
            importlib.import_module(modulename)
        except Exception as e:
            logger.exception(e)
            msg = _("Failed to load widget module: \n'{0}'")
            msg = msg.format(modulename)
            messagebox.showerror(_('Error'), msg)

    #initialize custom widgets
    for path in get_custom_widgets():
        dirname, fname = os.path.split(path)
        if fname.endswith('.py'):
            if dirname not in sys.path:
                sys.path.append(dirname)
            modulename = fname[:-3]
            try:
                importlib.import_module(modulename)
            except Exception as e:
                logger.exception(e)
                msg = _("Failed to load custom widget module: \n'{0}'")
                msg = msg.format(path)
                messagebox.showerror(_('Error'), msg)

#Initialize images
DESIGNER_DIR = os.path.dirname(os.path.abspath(__file__))
IMAGES_DIR = os.path.join(DESIGNER_DIR, "images")
StockImage.register_from_dir(IMAGES_DIR)
StockImage.register_from_dir(
    os.path.join(IMAGES_DIR, 'widgets', '22x22'), '22x22-')
StockImage.register_from_dir(
    os.path.join(IMAGES_DIR, 'widgets', '16x16'), '16x16-')


class StatusBarHandler(logging.Handler):
    def __init__(self, tklabel, level=logging.NOTSET):
        super(StatusBarHandler, self).__init__(level)
        self.tklabel = tklabel
        self._clear = True
        self._cb_id = None

    def emit(self, record):
        try:
            msg = self.format(record)
            if not self._clear and self._cb_id is not None:
                self.tklabel.after_cancel(self._cb_id)
            self._clear = False
            self._cb_id = self.tklabel.after(5000, self.clear)
            txtcolor = 'red'
            if record.levelno == logging.INFO:
                txtcolor = 'black'
            self.tklabel.configure(text=msg, foreground=txtcolor)
        except (KeyboardInterrupt, SystemExit):
            raise
        except:
            self.handleError(record)

    def clear(self):
        self.tklabel.configure(text='', foreground='black')
        self._clear = True


FILE_PATH = os.path.dirname(os.path.abspath(__file__))


class PygubuDesigner(object):
    """Main gui class"""
    
    def __init__(self):
        init_pygubu_widgets()        

        """Creates all gui widgets"""

        self.preview = None
        self.about_dialog = None
        self.preferences = None
        self.script_generator = None
        self.builder = pygubu.Builder(translator)
        self.currentfile = None
        self.is_changed = False
        self.current_title = 'new'

        uifile = os.path.join(FILE_PATH, "ui/pygubu-ui.ui")
        self.builder.add_from_file(uifile)
        self.builder.add_resource_path(os.path.join(FILE_PATH, "images"))

        #build main ui
        self.mainwindow = self.builder.get_object('mainwindow')
        #toplevel = self.master.winfo_toplevel()
        menu = self.builder.get_object('mainmenu', self.mainwindow)
        self.mainwindow.configure(menu=menu)

        #Class selector values
        self.widgetlist_sf = self.builder.get_object("widgetlist_sf")
        self.widgetlist = self.builder.get_object("widgetlist")
        self.configure_widget_list()

        #widget tree
        self.treeview = self.builder.get_object('treeview1')
        self.bindings_frame = self.builder.get_object('bindingsframe')
        self.bindings_tree = self.builder.get_object('bindingstree')

        #Preview
        previewc = self.builder.get_object('preview_canvas')
        self.previewer = PreviewHelper(previewc)
        #tree editor
        self.tree_editor = WidgetsTreeEditor(self)

        self.builder.connect_callbacks(self)

        #Status bar
        #self.statusbar = self.builder.get_object('statusbar')
        #handler = StatusBarHandler(self.statusbar)
        #handler.setLevel(logging.INFO)
        # add handler to the root logger:
        #logging.getLogger().addHandler(handler)

        #
        #Application bindings
        #
        master = self.mainwindow
        master.bind_all(
            '<Control-KeyPress-n>',
            lambda e: self.on_file_menuitem_clicked('file_new'))
        master.bind_all(
            '<Control-KeyPress-o>',
            lambda e: self.on_file_menuitem_clicked('file_open'))
        master.bind_all(
            '<Control-KeyPress-s>',
            lambda e: self.on_file_menuitem_clicked('file_save'))
        master.bind_all(
            '<Control-KeyPress-q>',
            lambda e: self.on_file_menuitem_clicked('file_quit'))
        master.bind_all(
            '<Control-KeyPress-i>',
            lambda e: self.on_edit_menuitem_clicked('edit_item_up'))
        master.bind_all(
            '<Control-KeyPress-k>',
            lambda e: self.on_edit_menuitem_clicked('edit_item_down'))
        master.bind_all(
            '<F5>',
            lambda e: self.tree_editor.preview_in_toplevel())
        master.bind_all(
            '<F6>',
            lambda e: self.previewer.close_toplevel_previews())

        #
        # Widget bindings
        #
        self.tree_editor.treeview.bind(
            '<Control-KeyPress-c>',
            lambda e: self.tree_editor.copy_to_clipboard())
        self.tree_editor.treeview.bind(
            '<Control-KeyPress-v>',
            lambda e: self.tree_editor.paste_from_clipboard())
        self.tree_editor.treeview.bind(
            '<Control-KeyPress-x>',
            lambda e: self.tree_editor.cut_to_clipboard())
        self.tree_editor.treeview.bind(
            '<KeyPress-Delete>',
            lambda e: self.on_edit_menuitem_clicked('edit_item_delete'))

        def clear_key_pressed(event, newevent):
            # when KeyPress, not Ctrl-KeyPress, generate event.
            if event.keysym_num == ord(event.char):
                self.tree_editor.treeview.event_generate(newevent)
        self.tree_editor.treeview.bind('<i>',
                lambda e: clear_key_pressed(e, '<Up>'))
        self.tree_editor.treeview.bind('<k>',
                lambda e: clear_key_pressed(e, '<Down>'))

        #grid move bindings
        self.tree_editor.treeview.bind(
            '<Alt-KeyPress-i>',
            lambda e: self.on_edit_menuitem_clicked('grid_up'))
        self.tree_editor.treeview.bind(
            '<Alt-KeyPress-k>',
            lambda e: self.on_edit_menuitem_clicked('grid_down'))
        self.tree_editor.treeview.bind(
            '<Alt-KeyPress-j>',
            lambda e: self.on_edit_menuitem_clicked('grid_left'))
        self.tree_editor.treeview.bind(
            '<Alt-KeyPress-l>',
            lambda e: self.on_edit_menuitem_clicked('grid_right'))
            
        # On preferences save binding
        self.mainwindow.bind('<<PygubuDesignerPreferencesSaved>>', self.on_preferences_saved)

        #
        # Setup tkk styles
        #
        self._setup_styles()

        #
        # Setup dynamic theme submenu
        #
        self._setup_theme_menu()

        #app config
        top = self.mainwindow
        try:
            top.wm_iconname('pygubu')
            top.tk.call('wm', 'iconphoto', '.', StockImage.get('pygubu'))
        except StockImageException as e:
            pass
        
    def run(self):
        self.mainwindow.protocol("WM_DELETE_WINDOW", self.__on_window_close)
        self.mainwindow.mainloop()
    
    def __on_window_close(self):
        """Manage WM_DELETE_WINDOW protocol."""
        if self.on_close_execute():
            self.mainwindow.destroy()

    def quit(self):
        """Exit the app if it is ready for quit."""
        self.__on_window_close()
        
    def set_title(self, newtitle):
        self.current_title = newtitle
        default_title = 'Pygubu Designer - {0}'
        title = default_title.format(newtitle)
        self.mainwindow.wm_title(title)

    def _setup_styles(self):
        s = ttk.Style()
        s.configure('ColorSelectorButton.Toolbutton',
                    image=StockImage.get('mglass'))
        s.configure('ImageSelectorButton.Toolbutton',
                    image=StockImage.get('mglass'))
        if sys.platform == 'linux':
            #change background of comboboxes
            color = s.lookup('TEntry', 'fieldbackground')
            s.map('TCombobox', fieldbackground=[('readonly', color)])
            s.map('TSpinbox', fieldbackground=[('readonly', color)])

    def _setup_theme_menu(self):
        menu = self.builder.get_object('preview_themes_submenu')
        s = ttk.Style()
        styles = s.theme_names()
        self.__theme_var = var = tk.StringVar()
        var.set(s.theme_use())

        for name in styles:

            def handler(style=s, theme=name):
                style.theme_use(theme)

            menu.add_radiobutton(label=name, value=name,
                                 variable=self.__theme_var, command=handler)

    def create_treelist(self):
        root_tagset = set(('tk', 'ttk'))

        #create unique tag set
        tagset = set()
        for c in builder.CLASS_MAP.keys():
            wc = builder.CLASS_MAP[c]
            tagset.update(wc.tags)
        tagset.difference_update(root_tagset)

        treelist = []
        for c in builder.CLASS_MAP.keys():
            wc = builder.CLASS_MAP[c]
            ctags = set(wc.tags)
            roots = (root_tagset & ctags)
            sections = (tagset & ctags)
            for r in roots:
                for s in sections:
                    key = '{0}>{1}'.format(r, s)
                    treelist.append((key, wc))

        #sort tags by label
        def by_label(t):
            return "{0}{1}".format(t[0], t[1].label)
        treelist.sort(key=by_label)
        return treelist
    
    def configure_widget_list(self):
        treelist = self.create_treelist()
        if get_option('widget_palette') == 'accordion':
            self.create_accordion_widget_list(treelist)
        else:
            self.create_treeview_widget_list(treelist)
        
    def create_treeview_widget_list(self, treelist):
        # sbhelper widget
        sbhelper = ScrollbarHelper(self.widgetlist, scrolltype='both')

        # widgetlisttv widget
        widgetlisttv = ttk.Treeview(sbhelper)
        widgetlisttv.configure(selectmode='browse', show='tree')
        widgetlisttv.grid(column='0', row='0', sticky='nsew')
        
        sbhelper.add_child(widgetlisttv)
        sbhelper.configure(usemousewheel='true')
        sbhelper.grid(column='0', row='0', sticky='nsew')
        
        #Default widget image:
        default_image = ''
        try:
            default_image = StockImage.get('22x22-tk.default')
        except StockImageException as e:
            pass

        #Start building widget tree selector
        roots = {}
        sections = {}
        for key, wc in treelist:
            root, section = key.split('>')
            #insert root
            if root not in roots:
                roots[root] = widgetlisttv.insert('', 'end', text=root)
            #insert section
            if key not in sections:
                sections[key] = widgetlisttv.insert(roots[root], 'end', text=section)
            #insert widget
            w_image = default_image
            try:
                w_image = StockImage.get('22x22-{0}'.format(wc.classname))
            except StockImageException as e:
                pass
            
            widgetlisttv.insert(sections[key], 'end', text=wc.label,
                image=w_image, tags='widget', values=(wc.classname,))
        widgetlisttv.tag_bind('widget', '<Double-1>', self.on_widgetlist_dclick)

        #Expand prefered widget set
        hidews = 'tk'
        prefws = get_option('widget_set')
        if hidews == prefws:
            hidews = 'ttk'
        widgetlisttv.item(roots[hidews], open=False)
        widgetlisttv.item(roots[prefws], open=True)
        for child in widgetlisttv.get_children(roots[prefws]):
            widgetlisttv.item(child, open=True)
    
    def on_widgetlist_dclick(self, event):
        tv = event.widget
        sel = tv.selection()
        if sel:
            item = sel[0]
            classname = tv.item(item, 'values')[0]
            self.on_add_widget_event(classname)
    
    def create_accordion_widget_list(self, treelist):
        acf = AccordionFrame(self.widgetlist)
        acf.grid(sticky=tk.NSEW)
        acf.bind('<<AccordionGroupToggle>>', self.on_widgetlist_group_toogle)

        #Default widget image:
        default_image = ''
        try:
            default_image = StockImage.get('22x22-tk.default')
        except StockImageException as e:
            pass

        #Start building widget tree selector
        roots = {}
        sections = {}
        for key, wc in treelist:
            root, section = key.split('>')
            #insert root
            if root not in roots:
                roots[root] = acf.add_group(root, root)
            #insert section
            if key not in sections:
                sectionacf = AccordionFrame(roots[root])
                sectionacf.grid(sticky=tk.NSEW, padx='5 0')
                sectionacf.bind('<<AccordionGroupToggle>>',
                                self.on_widgetlist_group_toogle)
                sectiongrp = sectionacf.add_group(key, section)
                sections[key] = AutoArrangeFrame(sectiongrp)
                sections[key].grid(sticky=tk.NSEW)

            #insert widget
            w_image = default_image
            try:
                w_image = StockImage.get('22x22-{0}'.format(wc.classname))
            except StockImageException as e:
                pass

            #define callback for button
            def create_cb(cname):
                return lambda: self.on_add_widget_event(cname)

            b = ttk.Button(sections[key], text=wc.label, image=w_image,
                           style='Toolbutton', command=create_cb(wc.classname))
            tooltip.create(b, wc.classname)
            b.grid()

        #Expand prefered widget set
        hidews = 'tk'
        prefws = get_option('widget_set')
        if hidews == prefws:
            hidews = 'ttk'
        acf.group_toogle(hidews)
        self.widgetlist_sf.reposition()

    def on_widgetlist_group_toogle(self, event=None):
        "Refresh widget list to reposition scrolledframe"

        self.widgetlist_sf.reposition()

    def on_add_widget_event(self, classname):
        "Adds a widget to the widget tree."""

        self.tree_editor.add_widget(classname)
        self.tree_editor.treeview.focus_set()

    def on_preferences_saved(self, event=None):
        children = self.widgetlist.winfo_children()
        if children:
            child = self.widgetlist.nametowidget(children[0])
            child.destroy()
        self.configure_widget_list()
    
    def on_close_execute(self):
        quit = True
        if self.is_changed:
            quit = messagebox.askokcancel(
                _('File changed'),
                _('Changes not saved. Quit anyway?'))
        if quit:
            #prevent tk image errors on python2 ?
            StockImage.clear_cache()
        return quit

    def do_save(self, fname):
        self.save_file(fname)
        self.currentfile = fname
        self.set_changed(False)
        logger.info(_('Project saved to {0}').format(fname))

    def do_save_as(self):
        options = {
            'defaultextension': '.ui',
            'filetypes': ((_('pygubu ui'), '*.ui'), (_('All'), '*.*'))}
        fname = filedialog.asksaveasfilename(**options)
        if fname:
            self.do_save(fname)

    def save_file(self, filename):
        xml_tree = self.tree_editor.tree_to_xml()
        util.indent(xml_tree.getroot())
        xml_tree.write(filename, xml_declaration=True, encoding='utf-8')
        title = self.project_name()
        self.set_title(title)

    def set_changed(self, newvalue=True):
        if newvalue and self.is_changed == False:
            self.set_title('{0} (*)'.format(self.current_title))
        self.is_changed = newvalue

    def load_file(self, filename):
        """Load xml into treeview"""

        self.tree_editor.load_file(filename)
        title = self.project_name()
        self.set_title(title)
        self.currentfile = filename
        self.set_changed(False)

    #File Menu
    def on_file_menuitem_clicked(self, itemid):
        if itemid == 'file_new':
            new = True
            if self.is_changed:
                new = openfile = messagebox.askokcancel(
                    _('File changed'),
                    _('Changes not saved. Discard Changes?'))
            if new:
                self.previewer.remove_all()
                self.tree_editor.remove_all()
                self.currentfile = None
                self.set_changed(False)
                self.set_title(self.project_name())
        elif itemid == 'file_open':
            openfile = True
            if self.is_changed:
                openfile = messagebox.askokcancel(
                    _('File changed'),
                    _('Changes not saved. Open new file anyway?'))
            if openfile:
                options = {
                    'defaultextension': '.ui',
                    'filetypes': ((_('pygubu ui'), '*.ui'), (_('All'), '*.*'))}
                fname = filedialog.askopenfilename(**options)
                if fname:
                    self.load_file(fname)
        elif itemid == 'file_save':
            if self.currentfile:
                if self.is_changed:
                    self.do_save(self.currentfile)
            else:
                self.do_save_as()
        elif itemid == 'file_saveas':
            self.do_save_as()
        elif itemid == 'file_quit':
            self.quit()

    #Edit menu
    def on_edit_menuitem_clicked(self, itemid):
        if itemid == 'edit_item_up':
            self.tree_editor.on_item_move_up(None)
        elif itemid == 'edit_item_down':
            self.tree_editor.on_item_move_down(None)
        elif itemid == 'edit_item_delete':
            do_delete = messagebox.askokcancel(_('Delete items'),
                                               _('Delete selected items?'))
            if do_delete:
                self.tree_editor.on_treeview_delete_selection(None)
        elif itemid == 'edit_copy':
            self.tree_editor.copy_to_clipboard()
        elif itemid == 'edit_paste':
            self.tree_editor.paste_from_clipboard()
        elif itemid == 'edit_cut':
            self.tree_editor.cut_to_clipboard()
        elif itemid == 'grid_up':
            self.tree_editor.on_item_grid_move(WidgetsTreeEditor.GRID_UP)
        elif itemid == 'grid_down':
            self.tree_editor.on_item_grid_move(WidgetsTreeEditor.GRID_DOWN)
        elif itemid == 'grid_left':
            self.tree_editor.on_item_grid_move(WidgetsTreeEditor.GRID_LEFT)
        elif itemid == 'grid_right':
            self.tree_editor.on_item_grid_move(WidgetsTreeEditor.GRID_RIGHT)
        elif itemid == 'edit_preferences':
            self._edit_preferences()

    #preview menu
    def on_previewmenu_action(self, itemid):
        if itemid == 'preview_toplevel':
            self.tree_editor.preview_in_toplevel()
        if itemid == 'preview_toplevel_closeall':
            self.previewer.close_toplevel_previews()

    #Help menu
    def on_help_menuitem_clicked(self, itemid):
        if itemid == 'help_online':
            url = 'https://github.com/alejandroautalan/pygubu/wiki'
            webbrowser.open_new_tab(url)
        elif itemid == 'help_about':
            self.show_about_dialog()
    
    # Project Menu
    def on_projectmenu_action(self, itemid):
        if itemid == 'generate_script':
            self.show_scriptgenerator()

    def _create_about_dialog(self):
        builder = pygubu.Builder(translator)
        uifile = os.path.join(FILE_PATH, "ui/about_dialog.ui")
        builder.add_from_file(uifile)
        builder.add_resource_path(os.path.join(FILE_PATH, "images"))

        dialog = builder.get_object(
            'aboutdialog', self.mainwindow)
        entry = builder.get_object('version')
        txt = entry.cget('text')
        txt = txt.replace('%version%', str(pygubu.__version__))
        entry.configure(text=txt)

        def on_ok_execute():
            dialog.close()

        builder.connect_callbacks({'on_ok_execute': on_ok_execute})

        return dialog

    def show_about_dialog(self):
        if self.about_dialog is None:
            self.about_dialog = self._create_about_dialog()
            self.about_dialog.run()
        else:
            self.about_dialog.show()

    def _edit_preferences(self):
        if self.preferences is None:
            self.preferences = PreferencesUI(self.mainwindow, translator)
        self.preferences.dialog.run()
        
    def project_name(self):
        name = None
        if self.currentfile is None:
            name = _('newproject')
        else:
            name = os.path.basename(self.currentfile)
        return name
    
    def show_scriptgenerator(self):
        if self.script_generator is None:
            self.script_generator = ScriptGenerator(self.mainwindow, translator)
        self.script_generator.configure(self.tree_editor, self.project_name())
        self.script_generator.run()


def start_pygubu():
    print("python: {0} on {1}".format(
                platform.python_version(), sys.platform))
    print("pygubu: {0}".format(pygubu.__version__))
    print("pygubu-designer: {0}".format(pygubudesigner.__version__))
    
    # Setup logging level
    parser = argparse.ArgumentParser()
    parser.add_argument('filename', nargs='?')
    parser.add_argument('--loglevel')
    args = parser.parse_args()
    
    loglevel = str(args.loglevel).upper()
    loglevel = getattr(logging, loglevel, logging.WARNING)
    logging.getLogger('').setLevel(loglevel)
    
    #
    # Dependency check
    #
    help = "Hint, If your are using Debian, install package python3-appdirs."
    if sys.version_info < (3,):
        help = "Hint, If your are using Debian, install package python-appdirs."
    check_dependency('appdirs', '1.3', help)    
    
    
    #root = tk.Tk()
    #root.withdraw()
    app = PygubuDesigner()
    #root.deiconify()

    filename = args.filename
    if filename is not None:
        app.load_file(filename)

    app.run()


def check_dependency(modulename, version, help_msg=None):
    try:
        module = importlib.import_module(modulename)        
        module_version = "<unknown>"
        for attr in ('version', '__version__', 'ver', 'PYQT_VERSION_STR'):
            v = getattr(module, attr, None)
            if v is not None:
                module_version = v
        msg = "Module {0} imported ok, version {1}"
        logger.info(msg.format(modulename, module_version))
    except ImportError as e:
        msg = """I can't import module "{module}". You need to have installed '{module}' version {version} or higher. {help}"""
        if help_msg is None:
            help_msg = ''
        msg = msg.format(module=modulename, version=version, help=help_msg)
        logger.error(msg)
        sys.exit(-1)


if __name__ == '__main__':
    start_pygubu()