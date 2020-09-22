# -*- coding:utf-8 -*-
from flask_restful import Resource, reqparse, request
from common.db import DB
from common.log import loggers
from common.utility import salt_api_for_product
from common.const import role_dict
from common.sso import access_required

logger = loggers()
parser = reqparse.RequestParser()
parser.add_argument("desc_path", type=str, required=True, trim=True)
parser.add_argument("target", type=list, required=True, trim=True)


# 获得所有的组
class ConfigGroups(Resource):
    @access_required(role_dict["common_user"])
    def get(self):
        db = DB()
        state, groups_list = db.select('groups', '')
        if state:
            return {"status": True, "message": "", "data": groups_list}, 200
        else:
            return {"status": False, "message": str(state)}, 500


# 处理分发
class Distribute(Resource):
    @access_required(role_dict["common_user"])
    def post(self):
        args = parser.parse_args()
        desc_path = args["desc_path"]
        target = args["target"]
        logger.info('desc:' + desc_path + " target:" + str(target))
        db = DB()
        target_minion_list = []
        for group_id in target:
            state, group = db.select_by_id('groups', group_id)
            if state:
                target_minion_list = target_minion_list + group["minion"]
            else:
                return {"status": False, "message": 'select group error'}, 500
        logger.info("target_minion_list:" + str(target_minion_list))

        state, result = db.select('product', "where data -> '$.name'='%s'" % 'config')
        product_config_id = result[0]['id']
        salt_api = salt_api_for_product(product_config_id)
        command = 'cat /home/111'
        result = salt_api.shell_remote_execution(target_minion_list, command)
        logger.info('result:' + str(result))
        return {"status": True, "message": 'success'}, 200