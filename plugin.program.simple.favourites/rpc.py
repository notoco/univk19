import sys
PY3 = sys.version_info.major >= 3

if PY3:
    from builtins import str, object

import json
#from xbmcswift2 import xbmc
import xbmc

class RPCType(type):
    def __getattr__(cls, category):
        return Category(category)

if PY3:
    class RPC(object, metaclass=RPCType):
        pass
else:
    class RPC(object):
        __metaclass__ = RPCType
    
class Category(object):
    def __init__(self, name):
        self.name = name
        
    def __str__(self):
        return self.name.title().replace("_", "")
    
    def __getattr__(self, method):
        return Method(self, method)


class Method(object):
    def __init__(self, category, name):
        self.category = category
        self.name = name
            
    def __str__(self):
        return self.name.title().replace("_", "")
        
    def __call__(self, **kwargs):
        method = "%s.%s" % (str(self.category), str(self))
        query = {"method": method, "params": kwargs}
        return json_query(query)
        
class RPCError(Exception):
    pass
    
def json_query(query):
    if not "jsonrpc" in query:
        query["jsonrpc"] = "2.0"
    if not "id" in query:
        query["id"] = 1
    
    xbmc_request = json.dumps(query)
    if PY3:
        response = json.loads(xbmc.executeJSONRPC(xbmc_request))
    else:
        raw = xbmc.executeJSONRPC(xbmc_request)
        clean = unicode(raw, 'utf-8', errors='ignore')
        response = json.loads(clean)
    if "error" in response:
        raise RPCError(response["error"])
    return response.get('result', response)

    
