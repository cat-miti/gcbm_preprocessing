import csv
import random
import numpy as np
import os
import logging
import inspect

import pgdata


class RollbackDistributor(object):
    def __init__(self, **age_proportions):
        self._rand = random.Random()
        self._ages = []
        for age, proportion in age_proportions.iteritems():
            self._ages.extend([age] * int(100.00 * proportion))

        self._rand.shuffle(self._ages)
        self._choices = {age: 0 for age in age_proportions.keys()}

    def __str__(self):
        return str(self._choices)

    def next(self):
        age = self._rand.choice(self._ages)
        self._choices[age] += 1
        return int(age)


class CalculateNewDistYr(object):
    def __init__(self, inventory_workspace, inventory_year,
                 inventory_field_names, rollback_start,
                 harv_yr_field, dist_age_prop_file_path):

        self.inventory_workspace = inventory_workspace
        self.inventory_field_names = inventory_field_names
        self.rollback_start = rollback_start
        self.inv_vintage = inventory_year
        self.harv_yr_field = harv_yr_field
        self.dist_age_prop_file_path = dist_age_prop_file_path
        self.db = pgdata.connect()

    def calculateNewDistYr(self):
        logging.info("computing new disturbance years")
        self.inv_age_field = self.inventory_field_names['age']
        self.establishment_date_field = self.inventory_field_names['establishment_date']
        self.disturbance_yr = self.inventory_field_names['disturbance_yr']
        self.new_disturbance_field = self.inventory_field_names['new_disturbance_yr']
        self.inv_dist_date_diff_field = self.inventory_field_names['dist_date_diff']
        self.dist_type_field = self.inventory_field_names['dist_type']
        self.regen_delay_field = self.inventory_field_names['regen_delay']
        self.preDistAge = self.inventory_field_names['pre_dist_age']
        self.rollback_vintage_field = self.inventory_field_names['rollback_age']

        self.calculatePreDistAge(self.dist_age_prop_file_path)
        self.calculateRolledBackInvAge()

    def calculatePreDistAge(self, dist_age_prop_path):
        """
        This update is one execution per grid cell record

        It should be possible to apply the update to all cells at once...
        Maybe using this approach?
        https://dba.stackexchange.com/questions/55363/set-random-value-from-set/55364#55364
        """
        logging.info("Calculating pre disturbance age using '{}' to select age"
                     .format(dist_age_prop_path))
        dist_age_props = {}
        with open(dist_age_prop_path, "r") as age_prop_file:
            reader = csv.reader(age_prop_file)
            reader.next()  # skip header
            for dist_type, age, prop in reader:
                dist_type = int(dist_type)
                dist_ages = dist_age_props.get(dist_type)
                if not dist_ages:
                    dist_age_props[dist_type] = {}
                    dist_ages = dist_age_props[dist_type]
                dist_ages[age] = float(prop)
        age_distributors = {}
        for dist_type, age_props in dist_age_props.iteritems():
            age_distributors[dist_type] = RollbackDistributor(**age_props)
        for row in self.db['preprocessing.inventory_disturbed']:
            age_distributor = age_distributors.get(dist_type)
            #logging.info("Age picks for disturbance type {}:{}".format(dist_type, str(age_distributor)))
            sql = """
                UPDATE preprocessing.inventory_disturbed
                SET pre_dist_age = %s
                WHERE grid_id = %s
            """
            self.db.execute(sql, (age_distributor.next(), row['grid_id']))

    def calculateRolledBackInvAge(self):
        logging.info("calculating rollback inventory age")
        sql = """
            UPDATE preprocessing.inventory_disturbed
            SET rollback_age = pre_dist_age + %s - new_disturbance_yr
        """
        self.db.execute(sql)


class updateInvRollback(object):
    def __init__(self, inventory_workspace, inventory_year, inventory_field_names,
                 inventory_classifiers, rollbackInvOut, rollbackDisturbancesOutput, rollback_range,
                 resolution, sb_percent, reporting_classifiers):

        self.inventory_workspace = inventory_workspace
        self.inventory_year = inventory_year
        self.inventory_field_names = inventory_field_names
        self.inventory_classifiers = inventory_classifiers

        self.rollbackDisturbanceOutput = rollbackDisturbancesOutput
        self.rasterOutput = rollbackInvOut
        self.resolution = resolution
        self.slashburn_percent = sb_percent
        self.reporting_classifiers = reporting_classifiers

        #data
        self.RolledBackInventory = "inventory_gridded_1990"
        self.rollback_range = rollback_range
        self.inv_vintage = inventory_year
        self.rollback_start = rollback_range[0]

        #layers
        self.RolledBackInventory_layer = "RolledBackInventory_layer"
        self.gridded_inventory_layer = "gridded_inventory_layer"
        self.disturbedInventory_layer = "disturbedInventory_layer"

    def updateInvRollback(self):
        logging.info("updating rollback inventory")
        self.rollbackAgeNonDistStands()
        #self.generateSlashburn()
        #self.exportRollbackDisturbances()
        return 0 #self.exportRollbackInventory()

    def rollbackAgeNonDistStands(self):
        logging.info('Rolling back ages for age {}'.format(self.rollback_start))
        sql_path = os.path.join(os.path.dirname(inspect.stack()[0][1]), 'sql')
        db = pgdata.connect(sql_path=sql_path)
        db['preprocessing.inventory_rollback'].drop()
        db.execute(
            db.queries['inventory_rollback'],
            (self.inventory_year, self.rollback_start))

    def generateSlashburn(self):
        logging.info("generating rollback slashburn")
        year_range = range(self.rollback_range[0], self.rollback_range[1]+1)
        # print "Start of slashburn processing..."
        PercSBofCC = self.slashburn_percent

        self.arcpy.MakeFeatureLayer_management(self.RolledBackInventory_layer, "temp_rollback")
        expression1 = '{} = {}'.format(self.arcpy.AddFieldDelimiters("temp_rollback", self.dist_type_field), 2)
        logging.info('Making slashburn for the range {}-{}'.format(self.rollback_range[0],self.rollback_range[1]))
        logging.info('Selecting {}% of the harvest area in each year as slashburn and adding it to the rollback disturbances...'.format(PercSBofCC))
        # Create SB records for each timestep
        for year in range(self.rollback_range[0], self.rollback_range[1] + 1):
            expression2 = '{} = {}'.format(self.arcpy.AddFieldDelimiters("temp_rollback", self.new_disturbance_field), year)
            self.arcpy.SelectLayerByAttribute_management("temp_rollback", "NEW_SELECTION", expression2)
            self.arcpy.SelectLayerByAttribute_management("temp_rollback", "SUBSET_SELECTION", expression1)
            if int(self.arcpy.GetCount_management("temp_rollback").getOutput(0)) > 0:
                number_features = [row[0] for row in self.arcpy.da.SearchCursor("temp_rollback", "OBJECTID")]
                temp_rollback_count = int(self.arcpy.GetCount_management("temp_rollback").getOutput(0))
                features2Bselected = random.sample(number_features,(int(np.ceil(round(float(temp_rollback_count * PercSBofCC)/100)))))
                features2Bselected.append(0)
                features2Bselected = str(tuple(features2Bselected)).rstrip(',)') + ')'
                selectExpression = '{} IN {}'.format(self.arcpy.AddFieldDelimiters("temp_rollback", "OBJECTID"), features2Bselected)
                self.arcpy.SelectLayerByAttribute_management("temp_rollback","NEW_SELECTION", selectExpression)
                self.arcpy.CopyFeatures_management("temp_rollback","temp_SB")
                self.arcpy.CalculateField_management("temp_SB", "DistType", 13, "PYTHON", "")
                self.arcpy.Append_management("temp_SB", self.RolledBackInventory_layer)
            self.arcpy.SelectLayerByAttribute_management("temp_rollback", "CLEAR_SELECTION")

    def exportRollbackDisturbances(self):

        #Export rollback disturbances

        logging.info('Exporting rollback disturbances to {}'.format(self.rollbackDisturbanceOutput))
        dirname =  os.path.dirname(self.rollbackDisturbanceOutput)
        if not os.path.exists(dirname):
            os.makedirs(dirname)
        dissolveFields = [self.dist_type_field, self.new_disturbance_field,self.regen_delay_field, self.CELL_ID]
        selectClause =  "{} IS NOT NULL".format(self.new_disturbance_field)

        self.arcpy.SelectLayerByAttribute_management(self.RolledBackInventory_layer, "NEW_SELECTION", selectClause)
        self.arcpy.Dissolve_management(self.RolledBackInventory_layer, self.rollbackDisturbanceOutput, dissolveFields,
            "","SINGLE_PART","DISSOLVE_LINES")

    def exportRollbackInventory(self):

        logging.info('Exporting rolled back inventory rasters to {}'.format(self.rasterOutput))
        rasterMeta = []
        self.arcpy.env.overwriteOutput = True

        fields = {
            "age": self.inventory_field_names["rollback_age"],
            "species": self.inventory_field_names["species"]
        }

        for classifierName, fieldName in self.reporting_classifiers.items():
            if not classifierName in fields:
                fields.update({classifierName:fieldName})
            else:
                raise KeyError("duplicated reporting classifier: '{}'".format(classifierName))

        if not os.path.exists(self.rasterOutput):
            os.makedirs(self.rasterOutput)
        for classifier_name, classifier_attribute in self.inventory_classifiers.items():
            logging.info('Exporting classifer {} from {}'.format(classifier_name, os.path.join(self.inventory_workspace,self.RolledBackInventory)))
            field_name = classifier_attribute
            file_path = os.path.join(self.rasterOutput, "{}.tif".format(classifier_name))
            attribute_table_path = os.path.join(self.rasterOutput, "{}.tif.vat.dbf".format(classifier_name))
            self.arcpy.FeatureToRaster_conversion(self.RolledBackInventory, field_name, file_path, self.resolution)
            rasterMeta.append(
                {
                    "file_path": file_path,
                    "attribute": classifier_name,
                    "attribute_table": self.createAttributeTable(attribute_table_path, field_name)
                }
            )
        for attr in fields:
            logging.info('Exporting field {} from {}'.format(attr, os.path.join(self.inventory_workspace,self.RolledBackInventory)))
            field_name = fields[attr]
            file_path = os.path.join(self.rasterOutput,"{}.tif".format(attr))
            attribute_table_path = os.path.join(self.rasterOutput, "{}.tif.vat.dbf".format(attr))
            self.arcpy.FeatureToRaster_conversion(self.RolledBackInventory, field_name, file_path, self.resolution)
            rasterMeta.append(
                {
                    "file_path": file_path,
                    "attribute": attr,
                    "attribute_table": self.createAttributeTable(attribute_table_path, field_name)
                })

        return rasterMeta

    def createAttributeTable(self, dbf_path, field_name):
        # Creates an attribute table with the field name given
        # to be used in the tiler along with the tif. This is
        # necessary for fields that are not integers.
        attr_table = {}
        for row in DBF(dbf_path):
            if len(row)<3:
                return None
            attr_table.update({row.items()[0][1]: [row.items()[-1][1]]})
        return attr_table
