import os
import shutil
import time
import glob
import logging

import sass
import frontmatter
import markdown2
import htmlmin

from jinja2 import Environment, FileSystemLoader, select_autoescape, TemplateNotFound
from distutils.dir_util import copy_tree

from core.helpers import Expects, load_files, set_dir, get_cwd, cd_is_project, create_empty_directory

log = logging.getLogger(__name__)
# TODO: Make certain parts customizable via configuration file.
# TODO: This could do with some more logging so users understand whats going on


class Builder:
    """Builder class for Jackman projects. Builds a website from project files.

    Args:
        mode (str): Type of build. Defaults to 'production' - which dispatches the build to _website directory.

    Attributes:
        mode (str): Type of build. Defaults to 'production' - which dispatches the build to _website directory.
        images (dict): Dictionary with all images in the project directory.
        tmp_dir (str): Path to the temporary directory used for building before dispatching.
        jinja_environment (jinja2.environment): The Jinja environment to use when building.
    """

    def __init__(self, mode="production"):
        self.mode = mode
        self.images = {}
        self.directory = get_cwd() if cd_is_project() else None

        # Create a temporary folder to write the build to, so we can rollback at any time
        self.tmp_dir = f'_tmp_{int(time.time())}'
        os.mkdir(self.tmp_dir, 0o755)
        log.debug(f'Created temporary directory with name {self.tmp_dir}')
        self.jinja_environment = None

    def build(self):
        """Public build function. Call to this function builds the project directory to _website.

        Returns:
            None
        """
        if not cd_is_project():
            set_dir(self.directory)

        self._load_templates()
        self.jinja_environment = self._create_jinja_env()

        try:
            log.info('Loading references to all images')
            self.images = load_files('_static/images/')
            for image in self.images:
                self._copy_to_tmp(f'_static/images/{image}', 'images/')
        except FileNotFoundError:
            log.info('Could not find _static/images. The directory is missing or you lack the proper permission.')

        self._build_pages()
        self._build_posts()
        self._build_styles()
        self._clean_tmp()

        if not self.mode == 'development':
            self._dispatch_build()

    def _copy_to_tmp(self, path, sub_folder=''):
        """Copies a file to the temporary working directory.

        Args:
            path (str): The relative path to the file to copy.
            sub_folder (str): The directory in the temporary directory to copy the file to. Defaults to ''.

        Returns:
            None
        """
        if sub_folder != '' and not os.path.exists(f'{self.tmp_dir}/{sub_folder}'):
            os.mkdir(f'{self.tmp_dir}/{sub_folder}/')

        shutil.copy(path, f'{self.tmp_dir}/{sub_folder}')

    def _build_styles(self):
        """Copies .css to the temporary folder and builds .sass and .scss to .css to the temp folder.

        Note:
            In case of naming collision between .css and sass, will build sass on top of css. CSS overrules sass.

        Returns:
            None
        """
        create_empty_directory(f'{self.tmp_dir}/styles')
        if glob.glob('_static/styles/*.sass') or glob.glob('_static/styles/*.scss'):
            sass.compile(dirname=('static/styles/', f'{self.tmp_dir}/styles/'))
        for file in os.listdir('_static/styles/'):
            if file.endswith('.css'):
                self._copy_to_tmp(f'_static/styles/{file}', 'styles')

    def _build_markdown(self, file):
        """Builds a .md or .markdown file into a .html file.

        Args:
            file (tuple): Tuple containing the relative path (str) and extension (str) of the file to parse.

        Returns:
            None
        """
        path, extension = file
        with open(f'{self.tmp_dir}/{path}.{extension}') as f:
            data = frontmatter.loads(f.read())

        # Parse markdown to HTML
        html = markdown2.markdown(data.content, extras=["cuddled-lists"]).replace('\n\n', '\n').rstrip()

        # Parse data and add to a page dict
        page = {}
        for key in data.keys():
            page[key] = data[key]

        # Try to build the page with jinja and markdown
        try:
            template = self.jinja_environment.get_template(f'{data["template"]}.html')
            out = template.render(content=html, page=page, images=self.images)
            minified_output = self._minify_html(out)

            with open(f'{self.tmp_dir}/{path}.html', 'w') as f:
                f.writelines(minified_output)
        except TemplateNotFound:
            log.exception(f'Could not build {path}: template {data["template"]} not found.', exc_info=False)

    def _build_pages(self):
        """Builds all the pages in the /_pages directory.

        Returns:
            None
        """
        for page in os.listdir('_pages/'):
            if page.endswith('.md') or page.endswith('.markdown'):
                self._copy_to_tmp(f'_pages/{page}')
                file = (page.split('.')[0], page.split('.')[1])
                self._build_markdown(file)

    def _build_posts(self):
        """Builds all posts in the /_posts directory when they should be published.

        Returns:
            None
        """
        create_empty_directory(f'{self.tmp_dir}/posts')

    def _clean_tmp(self):
        """Cleans the temporary directory for any remaining artifacts.

        Returns:
            None
        """
        for file in os.listdir(f'{self.tmp_dir}'):
            if os.path.isdir(file) and file.startswith('_'):
                shutil.rmtree(f'{self.tmp_dir}/{file}')
            elif file.endswith('.md') or file.endswith('.markdown'):
                os.remove(f'{self.tmp_dir}/{file}')

    def _dispatch_build(self):
        """Safely clears the _website directory and dispatches the latest build into this directory.

        Returns:
            None
        """
        create_empty_directory('_website_new')

        # Make sure that the _website directory actually exists
        with Expects([FileExistsError]):
            os.mkdir('_website')

        copy_tree(self.tmp_dir, '_website_new')
        shutil.rmtree('_website')
        os.rename('_website_new', '_website')
        copy_tree(self.tmp_dir, '_website')
        shutil.rmtree(self.tmp_dir)

    def _create_jinja_env(self):
        """Creates a jinja2 environment with a PackageLoader.

        Returns:
            env (jinja2.Environment): The environment that was configured.

        TODO: Make this configurable.
        """
        env = Environment(
            loader=FileSystemLoader(f'{self.tmp_dir}/_templates'),
        )
        return env

    def _load_templates(self):
        """Loads templates into the temporary template directory.

        Returns:
            None
        """
        log.info('Loading templates into temporary template directory')
        start = time.time()
        for file in os.listdir('_templates/'):
            self._copy_to_tmp(f'_templates/{file}', '_templates')
        log.debug(f'Done loading templates in {round(time.time() - start, 5)} seconds')

    @staticmethod
    def _minify_html(html):
        """Minifies the HTML for optimization purposes.

        Args:
            html (str): The formatted HTML code to be minified.

        Returns:
            str: The minified HTML code.

        TODO: Make settings configurable
        """
        minified_html = htmlmin.minify(html,
                                       remove_comments=True,
                                       remove_empty_space=True,
                                       remove_all_empty_space=False,
                                       reduce_empty_attributes=True,
                                       reduce_boolean_attributes=False,
                                       remove_optional_attribute_quotes=True,
                                       convert_charrefs=True,
                                       keep_pre=False
                                       )
        return minified_html


def main():
    """Main entry point. Sets up the class and builds the entire website to the _website directory
    """
    builder = Builder()
    builder.build()