import json

class RollbackConfig(object):
    def __init__(self, configPath, pathRegistry):
        self.config = self.loadJson(configPath)
        self.pathRegistry = pathRegistry

    def loadJson(self, path):
        with open(path) as json_data:
            return json.load(json_data)

    def GetInventoryWorkspace(self, region_path):
        x = self.config["Inventory_Workspace"]
        return self.pathRegistry.UnpackPath(x, region_path)

    def GetInventoryYear(self):
        return self.config["Inventory_Year"]

    def GetInventoryFieldNames(self):
        return self.config["Inventory_FieldNames"]

    def GetSpatialBoundariesAreaFilter(self):
        return self.config["Spatial_Boundaries_Area_Filter"]

    def GetRollbackRange(self):
        return [self.config["Rollback_Range"]["StartYear"],
                self.config["Rollback_Range"]["EndYear"]]

    def GetHistoricHarvestYearField(self):
        return self.config["HistoricHarvestYearField"]

    def GetInventoryRasterOutputDir(self, region_path):
        x = self.config["InventoryRasterOutputDir"]
        return self.pathRegistry.UnpackPath(x, region_path)

    def GetRollbackDisturbancesOutput(self, region_path):
        x = self.config["RollBackDisturbancesOutput"]
        return self.pathRegistry.UnpackPath(x, region_path)

    def GetResolution(self):
        return float(self.config["Resolution"])

    def GetSlashBurnPercent(self):
        x = float(self.config["SlashburnPercent"])
        if x<0 or x >100:
            raise ValueError("configuration slashburn percent out of range." \
                + "expected 0<=x<=100, got: {}".format(x))

    def GetReportingClassifiers(self):
        return self.config["Reporting_Classifiers"]

    def GetRollbackDisturbances(self, region_path):
        x = self.config["RollBackDisturbancesOutput"]
        return self.pathRegistry.UnpackPath(x, region_path)


