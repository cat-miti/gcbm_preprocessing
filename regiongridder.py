import os
import sys
import argparse

from loghelper import *

from grid.grid_inventory import GridInventory

from configuration.pathregistry import PathRegistry
from configuration.subregionconfig import SubRegionConfig
from configuration.preprocessorconfig import PreprocessorConfig
from preprocess_tools import postgis_manage

def main():

    create_script_log(sys.argv[0])

    try:
        parser = argparse.ArgumentParser(description="region preprocessor")
        parser.add_argument("--pathRegistry", help="path to file registry data")

        parser.add_argument("--preprocessorConfig", help=(
            "path to preprocessor configuration"))
        parser.add_argument("--subRegionConfig", help="path to sub region data")
        parser.add_argument("--subRegionNames", help=(
            "optional comma delimited string of sub region names (as defined in "
            "subRegionConfig) to process, if unspecified all regions will be "
            "processed"))

        args = parser.parse_args()

        
        pathRegistry = PathRegistry(os.path.abspath(args.pathRegistry))
        preprocessorConfig = PreprocessorConfig(os.path.abspath(args.preprocessorConfig),pathRegistry)

        subRegionConfig = SubRegionConfig(
            os.path.abspath(args.subRegionConfig),
            args.subRegionNames.split(",") if args.subRegionNames else None)


        logging.info("Run region gridder at resolution {}".format(preprocessorConfig.GetResolution()))


        # note that looping through regions will not currently work, table names
        # in the postgres db are equivalent for each region.
        for r in subRegionConfig.GetRegions():
            region_path = r["PathName"]

            
            root_postgis_var_path = pathRegistry.GetPath(
                "PostGIS_Connection_Vars")

            region_postgis_var_path = pathRegistry.GetPath(
                "PostGIS_Region_Connection_Vars",
                region_path=region_path)

            root_postgis_vars = postgis_manage.get_connection_variables(
                root_postgis_var_path)

            region_postgis_vars = root_postgis_vars.copy()

            region_postgis_vars["PGDATABASE"] = postgis_manage.generate_unique_db_name()
            postgis_manage.save_connection_variables(
               region_postgis_var_path,
                **region_postgis_vars)
            postgis_manage.create_database(root_postgis_var_path, region_postgis_vars["PGDATABASE"])
            postgis_manage.create_preprocessing_schema(region_postgis_var_path)

            workspace = preprocessorConfig.GetInventoryWorkspace(region_path)
            workspaceFilter = preprocessorConfig.GetInventoryFilter()
            gridInventory = GridInventory(preprocessorConfig)
            gridInventory.load_to_postgres(
                workspace,
                workspaceFilter)
            gridInventory.create_blocks()
            gridInventory.create_grid()
            gridInventory.grid_inventory()
    except Exception as ex:
        logging.exception("error")
        sys.exit(1)

    logging.info("all gridder tasks finished")


if __name__ == "__main__":
    main()
