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
parser.add_argument("file_path", type=str, default='', trim=True)
parser.add_argument("target", type=str, required=True, action="append")


# 获得所有的组
class ConfigGroups(Resource):
    @access_required(role_dict["common_user"])
    def get(self):
        db = DB()
        state, groups_list = db.select('groups', '')
        if state:
            db.close_mysql()
            return {"status": True, "message": "", "data": groups_list}, 200
        else:
            db.close_mysql()
            return {"status": False, "message": str(state)}, 500


# 处理分发
class Distribute(Resource):
    @access_required(role_dict["common_user"])
    def post(self):
        args = parser.parse_args()
        desc_path = args["desc_path"]
        target = args["target"]
        file_path = args["target"]
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
        master_id = result[0]['salt_master_id']
        logger.info('master_id:' + master_id)
        salt_api = salt_api_for_product(product_config_id)
        logger.info(str(salt_api))
        source_path = '/tmp/config/' + file_path
        logger.info(source_path)
        logger.info(target_minion_list[0])
        for minion_id in target_minion_list:
            logger.info('minion_id:' + minion_id)
            # command_path = 'mkdir -p ' + desc_path
            # logger.info("command_path:" + command_path)
            # result = salt_api.shell_remote_execution([minion_id], command_path)
            # logger.info("result1:" + str(result))
            # command_distribute = 'salt-cp ' + minion_id + ' ' + source_path + ' ' + desc_path
            # command = 'cd /tmp/config \n git pull \n' + command_distribute
            # logger.info('command' + command)
            # result = salt_api.shell_remote_execution([master_id], command)
            # logger.info("result2:" + str(result))
        db.close_mysql()
        return {"status": True, "message": 'success'}, 200



# 获得所有的主机
class ConfigHosts(Resource):
    @access_required(role_dict["common_user"])
    def get(self):
        db = DB()
        state, hosts_list = db.select('host', '')
        if state:
            db.close_mysql()
            return {"status": True, "message": "", "data": hosts_list}, 200
        else:
            db.close_mysql()
            return {"status": False, "message": str(state)}, 500


# 处理同步
class Synchronize(Resource):
    @access_required(role_dict["common_user"])
    def post(self):
        args = parser.parse_args()
        desc_path = args["desc_path"]
        target = args["target"]
        db = DB()
        state, result = db.select('product', "where data -> '$.name'='%s'" % 'config')
        product_config_id = result[0]['id']
        salt_api = salt_api_for_product(product_config_id)
        command = 'cat /home/111'
        result = salt_api.shell_remote_execution(target, command)
        logger.info('result:' + str(result))
        db.close_mysql()
        return {"status": True, "message": 'success'}, 200
