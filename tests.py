import unittest
import syg
import requests_mock
import json
import base64

class TestCommandLine(unittest.TestCase):
    def test_no_url(self):
        self.assertRaises(syg.SygSyntaxException, syg.main, "")
    def test_bad_url(self):
        self.assertRaises(syg.SygSyntaxException, syg.main, "nope")
    def test_wrong_url(self):
        self.assertRaises(syg.SygSyntaxException, syg.main, "https://ubuntu.com/404")
    def test_wrong_github_url(self):
        self.assertRaises(syg.SygSyntaxException, syg.main, "https://github.com/")
    def test_unrepo_github_url(self):
        self.assertRaises(syg.SygSyntaxException, syg.main, "https://github.com/no/no/no")
    def test_unrepo_github_url(self):
        self.assertRaises(syg.SygSyntaxException, syg.main, "https://github.com/")
    def test_http_github_url(self):
        self.assertRaises(syg.SygSyntaxException, syg.main, "http://github.com/snapcore/snapcraft")
    def test_happy(self):
        inputurl = "https://github.com/snapcore/snapcraft"
        output = syg.main(inputurl)
        self.assertEqual(output[1], inputurl)
        self.assertEqual(output[0], "https://api.github.com/repos/snapcore/snapcraft")
    def test_happy_git(self):
        inputurl = "https://github.com/snapcore/snapcraft"
        output = syg.main(inputurl + ".git")
        self.assertEqual(output[1], inputurl)
        self.assertEqual(output[0], "https://api.github.com/repos/snapcore/snapcraft")

@requests_mock.mock()
class TestBasicHandler(unittest.TestCase):
    NAME = "dunno"
    VERSION = "1.0.2"
    SUMMARY = "some app or other"
    def basic_request(self, m):
        m.get("https://api.github.com/repos/madeup1/madeup2", text=json.dumps({
            "name": self.NAME,
            "trees_url": "internal://trees{/sha}",
            "default_branch": "strange",
            "description": self.SUMMARY,
            "releases_url": "internal://releases{/id}"
        }))
        m.get("internal://trees/strange", text=json.dumps({
            "tree": []
        }))
        m.get("internal://releases/latest", text=json.dumps({
            "tag_name": self.VERSION
        }))
        return syg.process_repo("https://api.github.com/repos/madeup1/madeup2",
            "https://github.com/madeup1/madeup2", "madeup1", "madeup2")

    def test_called_both(self, m):
        output = self.basic_request(m)
        self.assertEqual(m.call_count, 3)

    def test_name(self, m):
        output = self.basic_request(m)
        self.assertEqual(output.get("name"), self.NAME)
    def test_version(self, m):
        output = self.basic_request(m)
        self.assertEqual(output.get("version"), self.VERSION)
    def test_summary(self, m):
        output = self.basic_request(m)
        self.assertEqual(output.get("summary"), self.SUMMARY)
    def test_grade(self, m):
        output = self.basic_request(m)
        self.assertEqual(output.get("grade"), "stable")
    def test_confinement(self, m):
        output = self.basic_request(m)
        self.assertEqual(output.get("confinement"), "classic")

    def test_apps(self, m):
        output = self.basic_request(m)
        self.assertNotEqual(output.get("apps"), None)
    def test_apps_name(self, m):
        output = self.basic_request(m)
        self.assertEqual(len(output["apps"].keys()), 1)
        self.assertEqual(list(output["apps"].keys())[0], self.NAME)
    def test_apps_command(self, m):
        output = self.basic_request(m)
        self.assertNotEqual(output["apps"][self.NAME].get("command"), None)
    def test_apps_command_value(self, m):
        output = self.basic_request(m)
        self.assertEqual(output["apps"][self.NAME]["command"], self.NAME)

    def test_parts(self, m):
        output = self.basic_request(m)
        self.assertNotEqual(output.get("parts"), None)
    def test_parts_name(self, m):
        output = self.basic_request(m)
        self.assertEqual(len(output["parts"].keys()), 1)
        self.assertEqual(list(output["parts"].keys())[0], self.NAME)
    def test_parts_name_source(self, m):
        output = self.basic_request(m)
        self.assertEqual(output["parts"][self.NAME]["source"], self.CLONE_URL)
    @unittest.skip("haven't done versions yet")
    def test_parts_name_source(self, m):
        output = self.basic_request(m)
        self.assertEqual(output["parts"][self.NAME]["source-tag"], self.VERSION)
    def test_parts_name_source_type(self, m):
        output = self.basic_request(m)
        self.assertEqual(output["parts"][self.NAME]["source-type"], "git")

@requests_mock.mock()
class TestPythonHandler(unittest.TestCase):
    NAME = "dunno"
    CLONE_URL = "haha://its-the-clone-url"
    def basic_request(self, m):
        m.get("https://api.github.com/repos/madeup1/madeup2", text=json.dumps({
            "name": self.NAME,
            "trees_url": "internal://trees{/sha}",
            "default_branch": "strange",
            "clone_url": self.CLONE_URL
        }))
        m.get("internal://trees/strange", text=json.dumps({
            "tree": [{"path": "readme.txt"}, {"path": "requirements.txt"}]
        }))

        return syg.process_repo("https://api.github.com/repos/madeup1/madeup2",
            "https://github.com/madeup1/madeup2", "madeup1", "madeup2")

    def test_parts_name_python(self, m):
        output = self.basic_request(m)
        self.assertEqual(output["parts"][self.NAME]["plugin"], "python")
    @unittest.skip("we don't detect python version as yet")
    def test_parts_name_version(self, m):
        output = self.basic_request(m)
        self.assertEqual(output["parts"][self.NAME]["python-version"], "python3")

    def test_ignore_non_requirements_txt_project(self, m):
        m.get("https://api.github.com/repos/madeup1/madeup2", text=json.dumps({
            "name": self.NAME,
            "trees_url": "internal://trees{/sha}",
            "default_branch": "strange",
            "clone_url": self.CLONE_URL
        }))
        m.get("internal://trees/strange", text=json.dumps({
            "tree": [{"path": "something else.txt"}]
        }))

        output = syg.process_repo("https://api.github.com/repos/madeup1/madeup2",
            "https://github.com/madeup1/madeup2", "madeup1", "madeup2")
        self.assertEqual(output["parts"][self.NAME].get("python-version"), None)

@requests_mock.mock()
class TestCmakeHandler(unittest.TestCase):
    NAME = "dunno"
    CLONE_URL = "haha://its-the-clone-url"
    def basic_request(self, m):
        m.get("https://api.github.com/repos/madeup1/madeup2", text=json.dumps({
            "name": self.NAME,
            "trees_url": "internal://trees{/sha}",
            "default_branch": "strange",
            "clone_url": self.CLONE_URL
        }))
        m.get("internal://trees/strange", text=json.dumps({
            "tree": [{"path": "readme.txt"}, {"path": "CMakeLists.txt"}]
        }))

        return syg.process_repo("https://api.github.com/repos/madeup1/madeup2",
            "https://github.com/madeup1/madeup2", "madeup1", "madeup2")

    def test_parts_name_cmake(self, m):
        output = self.basic_request(m)
        self.assertEqual(output["parts"][self.NAME]["plugin"], "cmake")
    def test_apps_plugs_value(self, m):
        output = self.basic_request(m)
        self.assertEqual(output["apps"][self.NAME]["plugs"], 
            ["network", "network-bind", "unity7", "opengl"])

@requests_mock.mock()
class TestCmakeHandler(unittest.TestCase):
    NAME = "dunno"
    CLONE_URL = "haha://its-the-clone-url"
    def basic_request(self, m):
        m.get("https://api.github.com/repos/madeup1/madeup2", text=json.dumps({
            "name": self.NAME,
            "trees_url": "internal://trees{/sha}",
            "default_branch": "strange",
            "clone_url": self.CLONE_URL
        }))
        m.get("internal://trees/strange", text=json.dumps({
            "tree": [{"path": "readme.txt"}, {"path": "whatever.pro"}]
        }))

        return syg.process_repo("https://api.github.com/repos/madeup1/madeup2",
            "https://github.com/madeup1/madeup2", "madeup1", "madeup2")

    def test_parts_name_qmake(self, m):
        output = self.basic_request(m)
        self.assertEqual(output["parts"][self.NAME]["plugin"], "qmake")
    def test_apps_plugs_value(self, m):
        output = self.basic_request(m)
        self.assertEqual(output["apps"][self.NAME]["plugs"], 
            ["network", "network-bind", "unity7", "opengl"])

@requests_mock.mock()
class TestDebianHandler(unittest.TestCase):
    NAME = "dunno"
    CLONE_URL = "haha://its-the-clone-url"
    def basic_request(self, m):
        m.get("https://api.github.com/repos/madeup1/madeup2", text=json.dumps({
            "name": self.NAME,
            "trees_url": "internal://trees{/sha}",
            "default_branch": "strange",
            "clone_url": self.CLONE_URL
        }))
        m.get("internal://trees/strange", text=json.dumps({
            "tree": [
                {"path": "readme.txt", "type": "blob"}, 
                {"path": "debian", "url": "internal://trees/strange/debian", "type": "tree"}
            ]
        }))
        m.get("internal://trees/strange/debian", text=json.dumps({
            "tree": [
                {"path": "subreadme.txt", "type": "blob"}, 
                {"path": "control", "url": "internal://trees/strange/debian/control", "type": "blob"}
            ]
        }))

        ctrl_file_content = ("Package: com.example.package\n"
                "Name: Example Package\nBuild-Depends: pies (>=2.3), lard\n"
                "Conflicts: com.example.legacy")
        as_b64 = base64.b64encode(ctrl_file_content.encode("utf-8"))
        as_json = json.dumps({"content": as_b64.decode("utf-8")})
        m.get("https://api.github.com/repos/madeup1/madeup2/contents/debian/control", 
            text=as_json)

        return syg.process_repo("https://api.github.com/repos/madeup1/madeup2",
            "https://github.com/madeup1/madeup2", "madeup1", "madeup2")

    def test_called_four(self, m):
        output = self.basic_request(m)
        self.assertEqual(m.call_count, 4)

    def test_build_packages(self, m):
        output = self.basic_request(m)
        self.assertEqual(output["parts"][self.NAME]["build-packages"], ["pies", "lard"])

class TestSerialiser(unittest.TestCase):
    def test_basic(self):
        self.assertEqual(
            syg.serialise({"name": "myname", "pies": "many"}),
            "name: myname\npies: many\n"
            )

@requests_mock.mock()
class TestTreeGetter(unittest.TestCase):
    def basic_request(self, m):
        m.get("internal://trees/strange/subdir", text=json.dumps({
            "tree": [{"path": "subsubdir", "url": "internal://trees/strange/subdir/subsubdir", "type": "tree"}]
        }))
        m.get("internal://trees/strange/subdir/subsubdir", text=json.dumps({
            "tree": [{"path": "pies", "url": "internal://trees/strange/subdir/subsubdir/pies", "type": "blob"}]
        }))
        initial_trees = {
            "tree": [{"path": "subdir", "url": "internal://trees/strange/subdir", "type": "tree"}]
        }
        tg = syg.get_tree_getter(initial_trees)
        result = tg(["subdir", "subsubdir"])
        return result

    def test_called_three(self, m):
        output = self.basic_request(m)
        self.assertEqual(m.call_count, 2)
    def test_output_count(self, m):
        output = self.basic_request(m)
        self.assertEqual(len(output), 1)
    def test_output_path(self, m):
        output = self.basic_request(m)
        self.assertEqual(output[0], "pies")

@requests_mock.mock()
class TestFileGetter(unittest.TestCase):
    def test_simple(self, m):
        m.get("https://api.github.com/repos/mrtest/myrepo/contents/fname", text=json.dumps({
            "content": base64.b64encode("ahaha".encode("utf-8")).decode("utf-8")
        }))
        tg = syg.get_file_getter("internal://base/repos/mrtest/myrepo", {}, "mrtest", "myrepo")
        result = tg("fname")
        self.assertEqual(result, b"ahaha")

if __name__ == '__main__':
    unittest.main()