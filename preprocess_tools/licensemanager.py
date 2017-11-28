import logging
import time
import os
from contextlib import contextmanager

# Fixes interaction between time and multiprocessing modules.
os.environ["FOR_DISABLE_CONSOLE_CTRL_HANDLER"] = "1"
os.environ["FOR_IGNORE_EXCEPTIONS"] = "1"

class Extensions(object):
    def __init__(self): raise RuntimeError("Not instantiable")

    GEOSTATS = "GeoStats"
    SPATIAL = "Spatial"
    
    @staticmethod
    def manages(name):
        return name in [Extensions.GEOSTATS, Extensions.SPATIAL]
        
    @staticmethod
    def checkout(extension):
        try:
            import archook
            archook.get_arcpy()
            import arcpy
            arcpy.CheckOutExtension(extension)
            return arcpy
        except:
            return None
            
    @staticmethod
    def release(extension):
        try:
            arcpy.CheckInExtension(extension)
        except:
            pass

  
class Products(object):
    def __init__(self): raise RuntimeError("Not instantiable")

    ARC         = "Arc"
    ARCINFO     = "ArcInfo"
    ARCEDITOR   = "ArcEditor"
    ARCVIEW     = "ArcView"
    
    @staticmethod
    def manages(name):
        return name in [Products.ARC, Products.ARCINFO, Products.ARCEDITOR, Products.ARCVIEW]
        
    @staticmethod
    def checkout(name):
        try:
            if name == Products.ARCINFO:   import arcinfo
            if name == Products.ARCEDITOR: import arceditor
            if name == Products.ARCVIEW:   import arcview
            import archook
            archook.get_arcpy()
            import arcpy
            return arcpy if arcpy.ProductInfo() != "NotInitialized" else None
        except:
            return None
    
    @staticmethod
    def release(name):
        try:
            if name == Products.ARCINFO:   del arcinfo
            if name == Products.ARCEDITOR: del arceditor
            if name == Products.ARCVIEW:   del arcview
            del arcpy
        except:
            pass
            

@contextmanager
def arc_license(product_or_extension):
    mgr = None
    for license_manager in (Products, Extensions):
        if license_manager.manages(product_or_extension):
            mgr = license_manager
    
    if not mgr:
        logging.fatal("Tried to acquire unsupported license: {}".format(product_or_extension))
        return
    
    wait_time = 60
    max_retries = 60**2 * 12 / wait_time # Retry for up to 12 hours
    
    attempt = 0
    try:
        license = None
        while not license and attempt < max_retries:
            try:
                license = mgr.checkout(product_or_extension)
            except:
                logging.info("Waiting for {} license...".format(product_or_extension))
                time.sleep(60)
            finally:
                attempt += 1
        
        if not license and attempt >= max_retries:
            logging.fatal("Failed to acquire {} after {} attempts.".format(product_or_extension, attempt))
            
        yield license
    finally:
        mgr.release(product_or_extension)