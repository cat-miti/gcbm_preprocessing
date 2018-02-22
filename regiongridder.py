from loghelper import *
from grid.create_grid import Fishnet
from grid.grid_inventory import GridInventory
from preprocess_tools.licensemanager import *
from configuration.pathregistry import PathRegistry
from configuration.subregionconfig import SubRegionConfig
from configuration.regiongridderconfig import RegionGridderConfig

import os, sys, argparse

class RegionGridder(object):

    def __init__(self, config, pathRegistry, fishnet, gridInventory):
        self.config = config
        self.pathRegistry = pathRegistry
        self.fishnet = fishnet
        self.gridInventory = gridInventory

    def ProcessSubRegion(self, region_path):
        workspace = self.config.GetInventoryWorkspace(
            self.pathRegistry, region_path)
        workspaceFilter = self.config.GetInventoryFilter()
        ageFieldName = self.config.GetInventoryAgeField()
        self.fishnet.createFishnet(workspace, workspaceFilter)
        self.gridInventory.gridInventory(workspace,
                                         workspaceFilter,
                                         ageFieldName)

    def Process(self, subRegionConfig, subRegionNames=None):
        regions = subRegionConfig.GetRegions() if subRegionNames is None \
            else [subRegionConfig.GetRegion(x) for x in subRegionNames]

        for r in regions:
            self.ProcessSubRegion(region_path = r["PathName"])

def main():

    create_script_log(sys.argv[0])
    parser = argparse.ArgumentParser(description="region preprocessor")
    parser.add_argument("--pathRegistry", help="path to file registry data")
    parser.add_argument("--regionGridderConfig", help="path to region gridder configuration")
    parser.add_argument("--subRegionConfig", help="path to sub region data")
    parser.add_argument("--subRegionNames", help="optional comma delimited "+
                        "string of sub region names (as defined in "+
                        "subRegionConfig) to process, if unspecified all "+
                        "regions will be processed")
    try:
        args = parser.parse_args()

        regionGridderConfig = RegionGridderConfig(os.path.abspath(args.regionGridderConfig))
        pathRegistry = PathRegistry(os.path.abspath(args.pathRegistry))
        subRegionConfig = SubRegionConfig(os.path.abspath(args.subRegionConfig))
        with arc_license(Products.ARC) as arcpy:
            fishnet = Fishnet(arcpy, regionGridderConfig.GetResolution())
            gridInventory = GridInventory(arcpy, regionGridderConfig.GetAreaMajorityRule())

            p = RegionGridder(
                config = regionGridderConfig,
                pathRegistry = pathRegistry,
                fishnet = fishnet,
                gridInventory = gridInventory)

            subRegionNames = args.subRegionNames.split(",") \
                if args.subRegionNames else None

            p.Process(subRegionConfig = subRegionConfig,
                        subRegionNames = subRegionNames)
    except Exception as ex:
        logging.exception("error")
        sys.exit(1)

if __name__ == "__main__":
    main()
