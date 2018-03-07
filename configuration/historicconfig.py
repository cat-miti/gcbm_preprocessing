
class HistoricConfig(object):
    def __init__(self, configPath, pathRegistry):
        self.config = self.loadJson(configPath)
        self.pathRegistry = pathRegistry

    def loadJson(self, path):
        with open(path) as json_data:
            return json.load(json_data)

    def GetResolution(self):
        return self.data["Resolution"]

    def GetAreaMajorityRule(self):
        return self.data["Area_Majority_Rule"]

    def GetInventoryWorkspace(self, region_path):
        return self.pathRegistry.UnpackPath(
            self.data["Inventory_Workspace"], region_path)

    def GetInventoryFilter(self):
        return self.data["Inventory_Filter"]

    def GetInventoryField(self, field):
        return self.data["Inventory_Field_Names"][field]

    def GetInventoryFieldNames(self):
        return self.config["Inventory_Field_Names"]

    def GetInventoryClassifiers(self):
        return self.config["Inventory_Classifiers"]

    def GetReportingClassifiers(self):
        return self.config["Reporting_Classifiers"]

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

    def GetSlashBurnPercent(self):
        x = float(self.config["SlashburnPercent"])
        if x<0 or x >100:
            raise ValueError("configuration slashburn percent out of range." \
                + "expected 0<=x<=100, got: {}".format(x))
        return x

    def GetRollbackDisturbances(self, region_path):
        x = self.config["RollbackDisturbances"]
        result = []
        for dist in x:
            result.append({
                "Workspace": self.pathRegistry.UnpackPath(dist["Workspace"], region_path),
                "WorkspaceFilter": dist["WorkspaceFilter"],
                "YearField": dist["YearField"]
            })
        return result

    def GetDistAgeProportionFilePath(self):
        return self.pathRegistry.UnpackPath(
            self.config["DistAgeProportionFilePath"])

    def GetTilerConfigPath(self, region_path):
        return self.pathRegistry.GetPath(
            "TilerConfigPath", region_path)
