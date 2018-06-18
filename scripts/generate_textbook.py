from subprocess import check_call
import os
import os.path as op
import shutil as sh
import yaml
from nbclean import NotebookCleaner
from tqdm import tqdm
import numpy as np
import argparse
DESCRIPTION = ("Convert a collection of Jupyter Notebooks into Jekyll "
               "markdown suitable for a course textbook.")

parser = argparse.ArgumentParser(description=DESCRIPTION)
parser.add_argument("--site_root", default=None, help="Path to the root of the textbook repository.")
parser.add_argument("--overwrite", action='store_true', help="Overwrite md files if they already exist.")
parser.add_argument("--execute", action='store_true', help="Execute notebooks before converting to MD.")
parser.set_defaults(overwrite=False, execute=False)


def _markdown_to_files(path_markdown, indent=2):
    """Takes a markdown file containing chapters/sub-headings and
    converts it to a file structure we can use to build a side bar."""

    with open(path_markdown, 'r') as ff:
        lines = ff.readlines()

    files = []
    for line in lines:
        if line.strip().startswith('* '):
            title = _between_symbols(line, '[', ']')
            link = _between_symbols(line, '(', ')')
            spaces = len(line) - len(line.lstrip(' '))
            level = spaces / indent
            files.append((title, link, level))
    return files


def _strip_suffixes(string, suffixes=None):
    """Remove suffixes so we can create links."""
    suffixes = ['.ipynb', '.md'] if suffixes is None else suffixes
    for suff in suffixes:
        string = string.replace(suff, '')
    return string


def _clean_lines(lines):
    """Replace images with jekyll image root and add escape chars as needed."""
    IMAGES_FOLDER_NAME = IMAGES_FOLDER.split(os.sep)[-1]
    IMG_STRINGS = [op.join(*(['..']*ii + [IMAGES_FOLDER_NAME])) for ii in np.arange(1, 5)[::-1]]  # To replace relative filepaths in markdown
    IMG_STRINGS.append(IMAGES_FOLDER)  # This is the nbconvert-generated name
    inline_replace_chars = ['#']
    for ii, line in enumerate(lines):
        # Images: replace relative image paths to baseurl paths
        for IMG_STRING in IMG_STRINGS:
            line = line.replace(IMG_STRING, '{{ site.baseurl }}/images')
        # Adding escape slashes since Jekyll removes them
        # Make sure we have at least two dollar signs and they
        # Aren't right next to each other
        dollars = np.where(['$' == char for char in line])[0]
        if len(dollars) > 2 and all(ii > 1 for ii in (dollars[1:] - dollars[:1])):
            for char in inline_replace_chars:
                line = line.replace('\\#', '\\\\#')
        line = line.replace(' \\$', ' \\\\$')
        lines[ii] = line
    return lines


def _generate_sidebar(files):
    """Generate the sidebar text for the textbook, and add it to the textbook yaml."""
    sidebar_text = []
    sidebar_text.append({'title': 'Home', 'class': 'level_0', 'url': '/'})
    chapter_ix = 1
    for ix_file, (title, link, level) in tqdm(list(enumerate(files))):
        if level > 0 and len(link) == 0:
            continue
        if level == 0:
            if site_yaml.get('number_chapters', False) is True:
                title = '{}. {}'.format(chapter_ix, title)
            chapter_ix += 1
        new_link = link.replace(NOTEBOOKS_FOLDER_NAME, TEXTBOOK_FOLDER_NAME.lstrip('_'))
        new_link = _strip_suffixes(new_link).lstrip('.')
        new_item = {'title': title, "class": "level_{}".format(int(level)), 'url': new_link}
        if level == 0:
            if ix_file != (len(files) - 1) and level < files[ix_file + 1][-1]:
                new_item['children'] = []
            sidebar_text.append(new_item)
        else:
            sidebar_text[-1]['children'].append(new_item)

        # Keep track of the URL for the first file in the textbook
        if ix_file == 0:
            textbook_yaml['first_chapter_url'] = new_link

    textbook_yaml['chapters'] = sidebar_text


def _between_symbols(string, c1, c2):
    """Grab characters between symbols in a string.
    Will return empty string if nothing is between c1 and c2."""
    for char in [c1, c2]:
        if char not in string:
            raise ValueError("Couldn't find character {} in string {}".format(
                char, string))
    return string[string.index(c1)+1:string.index(c2)]


if __name__ == '__main__':
    args = parser.parse_args()
    overwrite = bool(args.overwrite)
    execute = bool(args.execute)
    if args.site_root is None:
        args.site_root = op.join(op.dirname(op.abspath(__file__)), '..')

    # Paths for our notebooks
    SITE_ROOT = op.abspath(args.site_root)
    SITE_TEXTBOOK = op.join(SITE_ROOT, '_data', 'textbook.yml')
    CONFIG_FILE = op.join(SITE_ROOT, '_config.yml')
    TEMPLATE_PATH = op.join(SITE_ROOT, 'assets', 'templates', 'jekyllmd.tpl')
    TEXTBOOK_FOLDER_NAME = '_chapters'
    NOTEBOOKS_FOLDER_NAME = 'notebooks'
    TEXTBOOK_FOLDER = op.join(SITE_ROOT, TEXTBOOK_FOLDER_NAME)
    NOTEBOOKS_FOLDER = op.join(SITE_ROOT, NOTEBOOKS_FOLDER_NAME)
    IMAGES_FOLDER = op.join(SITE_ROOT, 'images')
    MARKDOWN_FILE = op.join(SITE_ROOT, 'SUMMARY.md')

    # Load the yaml for this site
    with open(CONFIG_FILE, 'r') as ff:
        site_yaml = yaml.load(ff.read())
    # Load the textbook ymal for this site
    with open(SITE_TEXTBOOK, 'r') as ff:
        textbook_yaml = yaml.load(ff.read())
    textbook_yaml = {} if textbook_yaml is None else textbook_yaml

    # --- Collect the files we'll convert over ---
    files = _markdown_to_files(MARKDOWN_FILE)

    # --- Loop through all ipynb/md files, convert to md as necessary and copy. ---
    for ix_file, (title, link, level) in tqdm(list(enumerate(files))):
        if len(link) == 0:
            continue
        if not op.exists(link):
            raise ValueError("Could not find file {}.".format(link))

        # Check new folder / file path
        filename = op.basename(link)
        new_folder = op.dirname(link).replace(NOTEBOOKS_FOLDER_NAME, TEXTBOOK_FOLDER_NAME)
        new_file_path = op.join(new_folder, filename.replace('.ipynb', '.md'))
        if overwrite is True and op.exists(new_file_path):
            continue

        if not op.isdir(new_folder):
            os.makedirs(new_folder)

        # Collect previous/next md file for pagination
        if ix_file == 0:
            prev_page_link = ''
            prev_file_title = ''
        else:
            prev_file_title, prev_page_link, _ = files[ix_file-1]
            prev_page_link = _strip_suffixes(prev_page_link.replace(NOTEBOOKS_FOLDER_NAME, TEXTBOOK_FOLDER_NAME))

        if ix_file == len(files) - 1:
            next_page_link = ''
            next_file_title = ''
        else:
            next_file_title, next_page_link, _ = files[ix_file+1]
            next_page_link = _strip_suffixes(next_page_link.replace(NOTEBOOKS_FOLDER_NAME, TEXTBOOK_FOLDER_NAME))

        # Convert notebooks or just copy md if no notebook.
        if link.endswith('.ipynb'):
            # Create a temporary version of the notebook we can modify
            tmp_notebook = link + '_TMP'
            sh.copy2(link, tmp_notebook)

            # Clean up the file before converting
            cleaner = NotebookCleaner(tmp_notebook)
            cleaner.remove_cells(empty=True)
            cleaner.remove_cells(search_text="# HIDDEN")
            cleaner.clear('stderr')
            cleaner.save(tmp_notebook)

            # Run nbconvert moving it to the output folder
            # This is the output directory for `.md` files
            build_call = '--FilesWriter.build_directory={}'.format(new_folder)
            # This is where images go - remove the _ so Jekyll will copy them over
            images_call = '--NbConvertApp.output_files_dir={}'.format(
                op.join(IMAGES_FOLDER, new_folder.lstrip('_')))
            call = ['jupyter', 'nbconvert', '--log-level="CRITICAL"',
                    '--to', 'markdown', '--template', TEMPLATE_PATH,
                    images_call, build_call, tmp_notebook]
            if execute is True:
                call.insert(-1, '--execute')
            check_call(call)
            os.remove(tmp_notebook)
        elif link.endswith('.md'):
            # If a non-notebook file, just copy it over.
            # If markdown we'll add frontmatter later
            sh.copy2(link, new_file_path)
        else:
            raise ValueError("Files must end in ipynb or md")

        # Extra slash to the inline math before `#` since Jekyll strips it
        with open(new_file_path, 'r') as ff:
            lines = ff.readlines()
        lines = _clean_lines(lines)

        # Front-matter YAML
        yaml_fm = []
        yaml_fm += ['---']
        if link.endswith('.ipynb'):
            yaml_fm += ['interact_link: {}'.format(link.lstrip('./'))]
        yaml_fm += ["title: '{}'".format(title)]
        yaml_fm += ['previouschapter:']
        yaml_fm += ['  url: {}'.format(prev_page_link.lstrip('._').replace('"', "'"))]
        yaml_fm += ["  title: '{}'".format(prev_file_title)]
        yaml_fm += ['nextchapter:']
        yaml_fm += ['  url: {}'.format(next_page_link.lstrip('._').replace('"', "'"))]
        yaml_fm += ["  title: '{}'".format(next_file_title)]
        if ix_file == 0 and site_yaml.get('textbook_only') is True:
            yaml_fm += ['redirect_from: /']
        yaml_fm += ['---']
        yaml_fm = [ii + '\n' for ii in yaml_fm]
        lines = yaml_fm + lines

        # Write the result
        with open(new_file_path, 'w') as ff:
            ff.writelines(lines)

    # Generate sidebar, replacing the old one if it exists
    _generate_sidebar(files)

    # Update textbook yaml
    with open(SITE_TEXTBOOK, 'w') as ff:
        yaml.dump(textbook_yaml, ff, default_flow_style=False)
    with open(SITE_TEXTBOOK, 'r') as ff:
        lines = '### PROGRAMATICALLY GENERATED, DO NOT MODIFY\n' + ff.read()
    with open(SITE_TEXTBOOK, 'w') as ff:
        ff.write(lines)

    print('Done generating sidebar...')
    print('Done!')
