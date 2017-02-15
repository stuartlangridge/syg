#!/usr/bin/python3

import sys, requests, yaml, collections, deb822, base64

#######################################################################
# Handlers
#######################################################################

def HandlerBasic(snap, repo, filenames, tree_getter, file_getter):
    # Guaranteed to be called first
    # Basic info, read from repo
    snap["name"] = repo.get("name", "(couldn't identify name)")
    snap["summary"] = repo.get("description", "(couldn't identify description)")

    # hardcoded basic info
    snap["grade"] = "stable"
    snap["confinement"] = "classic"

    actual_name = repo.get("name")
    if actual_name:
        snap["apps"] = {}
        snap["apps"][actual_name] = {"command": actual_name}

        snap["parts"] = {}
        snap["parts"][actual_name] = {
            "source": repo.get("clone_url", "(unknown)"),
            "source-tag": "(unknown)",
            "source-type": "git"
        }

def HandlerPython(snap, repo, filenames, tree_getter, file_getter):
    if not snap.get("parts"): return
    if "requirements.txt" not in filenames: return
    snap["parts"][snap["name"]] = {
        "plugin": "python",
        "python-version": "(choose python3 or python2)",
    }

def HandlerCmake(snap, repo, filenames, tree_getter, file_getter):
    if not snap.get("parts"): return
    if "CMakeLists.txt" not in filenames: return
    snap["parts"][snap["name"]] = {
        "plugin": "cmake",
        "qt-version": "(choose qt4 or qt5)"
    }
    snap["apps"][snap["name"]]["plugs"] = ["network", "network-bind", "unity7", "opengl"]

def HandlerQmake(snap, repo, filenames, tree_getter, file_getter):
    if not snap.get("parts"): return
    if len([x for x in filenames if x.endswith(".pro")]) == 0: return
    snap["parts"][snap["name"]] = {
        "plugin": "qmake",
        "qt-version": "(choose qt4 or qt5)"
    }
    snap["apps"][snap["name"]]["plugs"] = ["network", "network-bind", "unity7", "opengl"]

def HandlerDebian(snap, repo, filenames, tree_getter, file_getter):
    if not snap.get("parts"): return
    if "debian" not in filenames: return
    debian_filenames = tree_getter(["debian"])
    if "control" not in debian_filenames: return
    control = file_getter("debian/control")
    deb = deb822.Sources(control)
    buildDepsCNF = deb.relations.get("build-depends", [])
    buildDepsIndepCNF = deb.relations.get("build-depends-indep", [])
    buildDeps = []
    for node in buildDepsCNF + buildDepsIndepCNF:
        for dep in node:
            buildDeps.append(dep["name"])
    snap["parts"][snap["name"]]["build-packages"] = buildDeps


#######################################################################
# Infra
#######################################################################

class SygException(Exception): pass
class SygSyntaxException(SygException): pass
HEADERS = {'user-agent': 'popey/syg'}

def get_file_getter(apiurl, trees, owner, reponame):
    def getter(filename):
        """Fetch a specific file from the repo. Note that it is your responsibility
           to be sure that it exists. Check with a tree-getter first."""
        contents_url = "https://api.github.com/repos/%s/%s/contents/%s" % (owner, reponame, filename)
        r = requests.get(contents_url)
        out = r.json()
        file_content_b64 = out.get("content")
        if not file_content_b64:
            return None
        file_content = base64.b64decode(file_content_b64)
        return file_content
    return getter

def get_tree_getter(trees):
    def getter(folders):
        def next(current_tree):
            try:
                this_folder = folders.pop(0)
            except IndexError:
                return current_tree
            matches = [x["url"] for x in current_tree["tree"] 
                if x["path"] == this_folder and x["type"] == "tree"]
            if not matches: return None

            r = requests.get(matches[0], headers=HEADERS)
            return next(r.json())

        this_tree = next(trees)
        return [x["path"] for x in this_tree.get("tree", [])]
    return getter

def serialise(snap):
    # http://stackoverflow.com/a/8661021
    # http://stackoverflow.com/questions/9951852/pyyaml-dumping-things-backwards#comment26471464_17310199
    represent_dict_order = lambda self, data:  self.represent_mapping('tag:yaml.org,2002:map', data.items())
    yaml.SafeDumper.add_representer(collections.OrderedDict, represent_dict_order)
    return yaml.safe_dump(snap, default_flow_style=False)

def process_repo(apiurl, repourl, owner, reponame):
    r = requests.get(apiurl, headers=HEADERS)
    repo = r.json()
    trees_url = repo.get("trees_url")
    if not trees_url:
        print("Error: repository %s not found" % (repourl,))
        sys.exit(2)
    trees_url = trees_url.replace("{/sha}", "/%s" % repo.get("default_branch", "master"))
    r = requests.get(trees_url, headers=HEADERS)
    trees = r.json()
    filenames = [x["path"] for x in trees.get("tree", [])]

    snap = collections.OrderedDict()
    file_getter = get_file_getter(apiurl, trees, owner, reponame)
    tree_getter = get_tree_getter(trees)
    for h in HANDLERS:
        h(snap, repo, filenames, tree_getter, file_getter)
    return snap

def main(repourl):
    # Process the name
    if not repourl.startswith("https://github.com/"): raise SygSyntaxException
    if repourl.endswith(".git"):
        repourl = repourl[:-4]
    parts = repourl.split("/")
    if len(parts) != 5 or parts[0] != "https:" or parts[1] != "" or parts[2] != "github.com":
        raise SygSyntaxException
    owner, reponame = parts[3], parts[4]
    apiurl = "https://api.github.com/repos/%s/%s" % (owner, reponame)
    return (apiurl, repourl, owner, reponame)

HANDLERS = [
    HandlerBasic, # note that HandlerBasic must be first, so others can rely on snap["name"] etc existing
    HandlerPython,
    HandlerCmake,
    HandlerQmake,
    HandlerDebian
]

if __name__ == "__main__":
    try:
        if len(sys.argv) != 2: raise SygSyntaxException
        apiurl, repourl, owner, reponame = main(sys.argv[1])
        snap = process_repo(apiurl, repourl, owner, reponame)
        snapcraft_yaml = serialise(snap)
        fp = open("snapcraft.yaml", "w")
        fp.write(snapcraft_yaml)
        fp.close()
    except SygSyntaxException:
        print("Usage: syg <github HTTPS repository URL>\n"
            "(for example, https://github.com/snapcore/snapcraft)", file=sys.stderr)
        sys.exit(1)
