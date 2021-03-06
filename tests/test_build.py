from charmtools import build
from charmtools import utils
from path import path
from ruamel import yaml
import json
import logging
import mock
import os
import pkg_resources
import responses
import unittest


class TestBuild(unittest.TestCase):
    def setUp(self):
        self.dirname = path(pkg_resources.resource_filename(__name__, ""))
        os.environ["LAYER_PATH"] = self.dirname
        os.environ["INTERFACE_PATH"] = self.dirname / "interfaces"
        path("out").rmtree_p()

    def tearDown(self):
        path("out").rmtree_p()

    def test_tester_layer(self):
        bu = build.Builder()
        bu.log_level = "WARNING"
        bu.output_dir = "out"
        bu.series = "trusty"
        bu.name = "foo"
        bu.charm = "trusty/tester"
        bu.hide_metrics = True
        bu()
        base = path('out/trusty/foo')
        self.assertTrue(base.exists())

        # Verify ignore rules applied
        self.assertFalse((base / ".bzr").exists())

        # Metadata should have combined provides fields
        metadata = base / "metadata.yaml"
        self.assertTrue(metadata.exists())
        metadata_data = yaml.load(metadata.open())
        self.assertIn("shared-db", metadata_data['provides'])
        self.assertIn("storage", metadata_data['provides'])

        # Config should have keys but not the ones in deletes
        config = base / "config.yaml"
        self.assertTrue(config.exists())
        config_data = yaml.load(config.open())['options']
        self.assertIn("bind-address", config_data)
        self.assertNotIn("vip", config_data)

        cyaml = base / "layer.yaml"
        self.assertTrue(cyaml.exists())
        cyaml_data = yaml.load(cyaml.open())
        self.assertEquals(cyaml_data['includes'], ['trusty/mysql'])
        self.assertEquals(cyaml_data['is'], 'foo')
        self.assertEquals(cyaml_data['options']['mysql']['qux'], 'one')

        self.assertTrue((base / "hooks/config-changed").exists())

        # Files from the top layer as overrides
        start = base / "hooks/start"
        self.assertTrue(start.exists())
        self.assertIn("Overridden", start.text())

        self.assertTrue((base / "README.md").exists())
        self.assertEqual("dynamic tactics", (base / "README.md").text())

        sigs = base / ".build.manifest"
        self.assertTrue(sigs.exists())
        data = json.load(sigs.open())
        self.assertEquals(data['signatures']["README.md"], [
            u'foo',
            "static",
            u'cfac20374288c097975e9f25a0d7c81783acdbc81'
            '24302ff4a731a4aea10de99'])

        self.assertEquals(data["signatures"]['metadata.yaml'], [
            u'foo',
            "dynamic",
            u'01021a65fc131827805edfcbd4f81a897d'
            u'01a0415f2a20a1179035dc85473a5f'
            ])

        storage_attached = base / "hooks/data-storage-attached"
        storage_detaching = base / "hooks/data-storage-detaching"
        self.assertTrue(storage_attached.exists())
        self.assertTrue(storage_detaching.exists())
        self.assertIn("Hook: data", storage_attached.text())
        self.assertIn("Hook: data", storage_detaching.text())

    def test_regenerate_inplace(self):
        # take a generated example where a base layer has changed
        # regenerate in place
        # make some assertions
        bu = build.Builder()
        bu.log_level = "WARNING"
        bu.output_dir = "out"
        bu.series = "trusty"
        bu.name = "foo"
        bu.charm = "trusty/b"
        bu.hide_metrics = True
        bu()
        base = path('out/trusty/foo')
        self.assertTrue(base.exists())

        # verify the 1st gen worked
        self.assertTrue((base / "a").exists())
        self.assertTrue((base / "README.md").exists())

        # now regenerate from the target
        with utils.cd("out/trusty/foo"):
            bu = build.Builder()
            bu.log_level = "WARNING"
            bu.output_dir = path(os.getcwd())
            bu.series = "trusty"
            # The generate target and source are now the same
            bu.name = "foo"
            bu.charm = "."
            bu.hide_metrics = True
            bu()
            base = bu.output_dir
            self.assertTrue(base.exists())

            # Check that the generated layer.yaml makes sense
            cy = base / "layer.yaml"
            config = yaml.load(cy.open())
            self.assertEquals(config["includes"], ["trusty/a", "interface:mysql"])
            self.assertEquals(config["is"], "foo")

            # We can even run it more than once
            bu()
            cy = base / "layer.yaml"
            config = yaml.load(cy.open())
            self.assertEquals(config["includes"], ["trusty/a", "interface:mysql"])
            self.assertEquals(config["is"], "foo")

            # We included an interface, we should be able to assert things about it
            # in its final form as well
            provides = base / "hooks/relations/mysql/provides.py"
            requires = base / "hooks/relations/mysql/requires.py"
            self.assertTrue(provides.exists())
            self.assertTrue(requires.exists())

            # and that we generated the hooks themselves
            for kind in ["joined", "changed", "broken", "departed"]:
                self.assertTrue((base / "hooks" /
                                "mysql-relation-{}".format(kind)).exists())

            # and ensure we have an init file (the interface doesn't its added)
            init = base / "hooks/relations/mysql/__init__.py"
            self.assertTrue(init.exists())

    @responses.activate
    def test_remote_interface(self):
        # XXX: this test does pull the git repo in the response
        responses.add(responses.GET,
                      "http://interfaces.juju.solutions/api/v1/interface/pgsql/",
                      body='''{
                      "id": "pgsql",
                      "name": "pgsql4",
                      "repo":
                      "https://github.com/bcsaller/juju-relation-pgsql.git",
                      "_id": {
                          "$oid": "55a471959c1d246feae487e5"
                      },
                      "version": 1
                      }''',
                      content_type="application/json")
        bu = build.Builder()
        bu.log_level = "WARNING"
        bu.output_dir = "out"
        bu.series = "trusty"
        bu.name = "foo"
        bu.charm = "trusty/c-reactive"
        bu.hide_metrics = True
        bu()
        base = path('out/trusty/foo')
        self.assertTrue(base.exists())

        # basics
        self.assertTrue((base / "a").exists())
        self.assertTrue((base / "README.md").exists())
        # show that we pulled the interface from github
        init = base / "hooks/relations/pgsql/__init__.py"
        self.assertTrue(init.exists())
        main = base / "hooks/reactive/main.py"
        self.assertTrue(main.exists())

    @mock.patch("charmtools.utils.Process")
    @responses.activate
    def test_remote_layer(self, mcall):
        # XXX: this test does pull the git repo in the response
        responses.add(responses.GET,
                      "http://interfaces.juju.solutions/api/v1/layer/basic/",
                      body='''{
                      "id": "basic",
                      "name": "basic",
                      "repo":
                      "https://git.launchpad.net/~bcsaller/charms/+source/basic",
                      "_id": {
                          "$oid": "55a471959c1d246feae487e5"
                      },
                      "version": 1
                      }''',
                      content_type="application/json")
        bu = build.Builder()
        bu.log_level = "WARNING"
        bu.output_dir = "out"
        bu.series = "trusty"
        bu.name = "foo"
        bu.charm = "trusty/use-layers"
        bu.hide_metrics = True
        # remove the sign phase
        bu.PHASES = bu.PHASES[:-2]

        bu()
        base = path('out/trusty/foo')
        self.assertTrue(base.exists())

        # basics
        self.assertTrue((base / "README.md").exists())

        # show that we pulled charmhelpers from the basic layer as well
        mcall.assert_called_with(("pip3", "install",
                                  "--user", "--ignore-installed",
                                  mock.ANY), env=mock.ANY)

    @mock.patch("charmtools.utils.Process")
    def test_pypi_installer(self, mcall):
        bu = build.Builder()
        bu.log_level = "WARN"
        bu.output_dir = "out"
        bu.series = "trusty"
        bu.name = "foo"
        bu.charm = "trusty/chlayer"
        bu.hide_metrics = True

        # remove the sign phase
        bu.PHASES = bu.PHASES[:-2]
        bu()
        mcall.assert_called_with(("pip3", "install",
                                  "--user", "--ignore-installed",
                                  mock.ANY), env=mock.ANY)

    @mock.patch("path.Path.rmtree_p")
    @mock.patch("tempfile.mkdtemp")
    @mock.patch("charmtools.utils.Process")
    def test_wheelhouse(self, Process, mkdtemp, rmtree_p):
        mkdtemp.return_value = '/tmp'
        bu = build.Builder()
        bu.log_level = "WARN"
        bu.output_dir = "out"
        bu.series = "trusty"
        bu.name = "foo"
        bu.charm = "trusty/whlayer"
        bu.hide_metrics = True

        # remove the sign phase
        bu.PHASES = bu.PHASES[:-2]
        with mock.patch("path.Path.mkdir_p"):
            with mock.patch("path.Path.files"):
                bu()
                Process.assert_has_call((
                    '/tmp/bin/pip3', 'install',
                    '--no-binary', ':all:',
                    '-d', '/tmp',
                    'pip'))
                Process.assert_called_with((
                    '/tmp/bin/pip3', 'install',
                    '--no-binary', ':all:',
                    '-d', '/tmp',
                    '-r', self.dirname / 'trusty/whlayer/wheelhouse.txt'))

    @mock.patch.object(build.tactics, 'log')
    @mock.patch.object(build.tactics.YAMLTactic, 'read')
    def test_layer_options(self, read, log):
        entity = mock.MagicMock(name='entity')
        target = mock.MagicMock(name='target')
        config = mock.MagicMock(name='config')

        base_layer = mock.MagicMock(name='base_layer')
        base_layer.name = 'base'
        base = build.tactics.LayerYAML(entity, base_layer, target, config)
        base.data = {
            'defines': {
                'foo': {
                    'type': 'string',
                    'default': 'FOO',
                    'description': "Don't set me, bro",
                },
                'bar': {
                    'enum': ['yes', 'no'],
                    'description': 'Go to the bar?',
                },
            }
        }
        base.read()
        base._read = True
        top_layer = mock.MagicMock(name='top_layer')
        top_layer.name = 'top'
        top = build.tactics.LayerYAML(entity, top_layer, target, config)
        top.data = {
            'options': {
                'base': {
                    'bar': 'bah',
                },
            },
            'defines': {
                'qux': {
                    'type': 'boolean',
                    'default': False,
                    'description': "Don't set me, bro",
                },
            }
        }
        top.read()
        top._read = True
        top.combine(base)
        assert not top.lint()
        log.error.assert_called_with('Invalid value for option %s: %s',
                                     'base.bar',
                                     "'bah' is not one of ['yes', 'no']")

        log.error.reset_mock()
        top.data['options']['base']['bar'] = 'yes'
        assert top.lint()
        self.assertEqual(top.data['options'], {
            'base': {
                'foo': 'FOO',
                'bar': 'yes',
            },
            'top': {
                'qux': False,
            },
        })


if __name__ == '__main__':
    logging.basicConfig()
    unittest.main()
