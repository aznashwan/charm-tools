# Copyright (C) 2013 Marco Ceppi <marco@ceppi.net>.
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <http://www.gnu.org/licenses/>.

import os
import ConfigParser

from bzrlib import errors
from bzrlib.bzrdir import BzrDir
from bzrlib.branch import Branch
from bzrlib.plugin import load_plugins
from bzrlib.repository import Repository

load_plugins()


class Mr:
    def __init__(self, directory=None, config=None, trust_all=False):
        self.directory = directory or os.getcwd()
        self.control_dir = os.path.join(self.directory, '.bzr')
        self.trust_all = trust_all
        self.config_file = config or os.path.join(self.directory, '.mrconfig')

        if self._is_repository():
            self.config = self._read_cfg()
            self.bzr_dir = Repository.open(self.directory)
        else:
            self.config = ConfigParser.RawConfigParser()
            r = BzrDir.create(self.directory)
            self.bzr_dir = self.bzr_dir.create_repository(shared=True)

    def add(self, name=None, repository='lp:charms'):
        # This isn't a true conversion of Mr, as such it's highly specialized
        # for just Charm Tools. So when you "add" a charm, it's just going
        # to use the charm name to fill in a template. Repository is in there
        # just in case we later add personal branching.
        '''Add a respository to the mrconfig'''
        if not name:
            raise Exception('No name provided')
        if not self.config.has_section(name):
            self.config.add_section(name)

        self.config.set(name, 'checkout', os.path.join(repository, name))

        charm_remote = charm.split(' ')[-1]
        remote = Branch.open(charm_remote)
        remote.bzrdir.sprout(os.path.join(self.directory, charm))

        self._write_cfg()

    def checkout(self, charm=None):
        '''Checkout either one or all repositories from the mrconfig'''
        if not charm:
            for charm in self.config.sections():
                charm_remote = self._parse_checkout(charm)
                self._checkout(charm_remote,
                               os.path.join(self.directory, charm))
        else:
            # Move this, and the charm_* stuff to _checkout? Makes sense
            if not self.config.has_section(charm):
                raise Exception('No configuration for %s' % charm)

            charm_remote = self._parse_checkout(charm)
            self._checkout(charm_remote,
                           os.path.join(self.directory, charm))

    def update(self):
        '''Update, or checkout, a charm in to directory'''
        # Have this mirror checkout where it's all or one if charm is passed?
        for charm in self.config.sections():
            if not os.path.exists(os.join(self.directory, charm, '.bzr')):
                self.checkout(charm)
                continue

            charm_remote = self._parse_checkout(charm)
            local_branch = Branch.open(os.join(self.directory, charm))
            remote_branch = Branch.open(charm_remote)
            local_branch.pull(remote_branch)

    def remove(self, name=None):
        '''Remove a repository from the mrconfig'''
        if not name:
            raise Exception('No name provided')

        self.config.remove_section(name)
        self._write_cfg()

    def list(self):
        return self.config.sections()

    def _write_cfg(self):
        with open(self.config_file) as mrcfg:
            self.config.write(mrcfg)

    def _read_cfg(self):
        if not self.config_file:
            raise Exception('No .mrconfig specified')
        return ConfigParser.read(self.config_file)

    def _checkout(self, src, to):
        remote = Branch.open(src)
        remote.bzrdir.sprout(to)
        # I wish there was a way to 'close' a RemoteBranch. Sadly,
        # I don't think there is

    def _parse_checkout(self, charm):
        if not self.config.has_section(charm):
            raise Exception('No section %s configured' % charm)

        return self.config.get(charm, 'checkout').split(' ')[-1]

    def _is_repository(self):
        try:
            r = Repository.open(self.directory)
        except errors.NotBranchError:
            return False

        return r.is_shared()