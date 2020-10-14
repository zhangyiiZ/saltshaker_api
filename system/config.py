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
parser.add_argument("product_id", type=str, default='', trim=True)
parser.add_argument("project_id", type=str, default='', trim=True)
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
        file_path = args["file_path"]
        db = DB()
        target_minion_list = []
        for group_id in target:
            state, group = db.select_by_id('groups', group_id)
            if state:
                target_minion_list = target_minion_list + group["minion"]
            else:
                return {"status": False, "message": 'select group error'}, 500
        logger.info("target_minion_list:" + str(target_minion_list))

        state, product_result = db.select_by_id('product', args["product_id"])
        master_id = product_result['salt_master_id']
        salt_api = salt_api_for_product(args['product_id'])
        state, project_result = db.select_by_id('projects', args["project_id"])
        project_name = project_result["gitlab_name"]
        logger.info("project_name:" + project_name)
        file_path_list = str(file_path).rsplit('/',1)
        source_path = '/tmp/' + project_name + '/' + file_path
        source_path_tmp = '/tmp/' + project_name + '/' + file_path_list[0]+ '/tmp_file'
        no_success_minion_list = []
        for minion_id in target_minion_list:
            command_path = 'mkdir -p ' + desc_path
            salt_api.shell_remote_execution(minion_id, command_path)
            command_distribute = 'salt-cp ' + minion_id + ' ' + source_path_tmp + ' ' + desc_path
            command_list = []
            command_list.append('cd /tmp/' + project_name + ' \n ')
            command_list.append('git pull \n ')
            command_list.append('cp ' + source_path + ' ' + source_path_tmp + ' \n ')
            command_list.append(command_distribute + ' \n ')
            command_list.append('rm -f ' + source_path_tmp + ' \n ')
            command_final = ''.join(command_list)
            result = salt_api.shell_remote_execution([master_id], command_final)
            if not str(result).__contains__('True'):
                no_success_minion_list.append(minion_id)
        db.close_mysql()
        if len(no_success_minion_list)==0:
            return {"status": True, "message": 'success'}, 200
        else:
            return {"status": False, "message": '没有成功发送的节点有:'+str(no_success_minion_list)}, 500



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
