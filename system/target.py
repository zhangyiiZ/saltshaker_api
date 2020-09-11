# -*- coding:utf-8 -*-
import os

from flask_restful import Resource, reqparse, request
from flask import g, app
from common.log import loggers
from common.audit_log import audit_log
from common.db import DB
from common.utility import uuid_prefix, salt_api_for_product
from common.sso import access_required
import json

from common.xlsx import Xlsx
from fileserver.git_fs import gitlab_project
from resources.execute import verify_acl
from system.user import update_user_privilege, update_user_product
from common.const import role_dict
from fileserver.rsync_fs import rsync_config
from common.saltstack_api import SaltAPI
import gitlab

logger = loggers()

parser = reqparse.RequestParser()
parser.add_argument("host_id", type=str, required=True, trim=True)
parser.add_argument("target", type=str, default='', trim=True)
parser.add_argument("IP", type=str, default='', trim=True)
parser.add_argument("location", type=str, default='', trim=True)
parser.add_argument("model", type=str, default='', trim=True)
parser.add_argument("type", type=str, default='', trim=True)
parser.add_argument("project", type=str, default='', trim=True)
parser.add_argument("client", type=str, default='', trim=True)
parser.add_argument("pool", type=str, default='', trim=True)
parser.add_argument("path", type=str, default='/usr/local/prometheus/conf.d/', trim=True)
parser.add_argument("key_word", type=str, default='', trim=True)
parser.add_argument("file_name", type=str, default='', trim=True)


class Target(Resource):
    @access_required(role_dict["common_user"])
    def get(self, target_id):
        db = DB()
        status, result = db.select_by_id("target", target_id)
        db.close_mysql()
        if status is True:
            if result:
                return {"data": result, "status": True, "message": ""}, 200
            else:
                return {"status": False, "message": "%s does not exist" % target_id}, 404
        else:
            return {"status": False, "message": result}, 500

    @access_required(role_dict["product"])
    def delete(self, target_id):
        user = g.user_info["username"]
        db = DB()
        status, result = db.delete_by_id("target", target_id)
        db.close_mysql()
        if status is not True:
            logger.error("Delete product error: %s" % result)
            return {"status": False, "message": result}, 500
        if result is 0:
            return {"status": False, "message": "%s does not exist" % target_id}, 404
        audit_log(user, target_id, target_id, "product", "delete")
        info = update_user_privilege("product", target_id)
        if info["status"] is False:
            return {"status": False, "message": info["message"]}, 500
        # 更新Rsync配置
        rsync_config()
        return {"status": True, "message": ""}, 200

    @access_required(role_dict["product"])
    def put(self, target_id):
        user = g.user_info["username"]
        args = parser.parse_args()
        logger.info(args['host_id'])
        args["id"] = target_id
        target = args
        db = DB()
        # 判断是否存在
        select_status, select_result = db.select_by_id("target", target_id)
        if select_status is not True:
            db.close_mysql()
            logger.error("Modify target error: %s" % select_result)
            return {"status": False, "message": select_result}, 500
        if not select_result:
            db.close_mysql()
            return {"status": False, "message": "%s does not exist" % target_id}, 404
        # 判断名字是否重复
        status, result = db.select("target", "where data -> '$.name'='%s'" % args["target"])
        if status is True:
            if result:
                if target_id != result[0].get("id"):
                    db.close_mysql()
                    return {"status": False, "message": "The target already exists"}, 200
        status, result = db.update_by_id("target", json.dumps(target, ensure_ascii=False), target_id)
        db.close_mysql()
        if status is not True:
            logger.error("Modify target: %s" % result)
            return {"status": False, "message": result}, 500
        audit_log(user, args["id"], target_id, "target", "edit")
        return {"status": True, "message": result}, 200


class TargetList(Resource):
    @access_required(role_dict["common_user"])
    def get(self):
        logger.info("TargetLIST")
        host_id = request.args.get("host_id")
        db = DB()
        status, result = db.select("target", "where data -> '$.host_id'='%s'" % host_id)
        if status is True:
            target_list = result
        else:
            db.close_mysql()
            return {"status": False, "message": result}, 500
        db.close_mysql()
        return {"data": target_list, "status": True, "message": ""}, 200

    @access_required(role_dict["product"])
    def post(self):
        args = parser.parse_args()
        args["id"] = uuid_prefix("p")
        user = g.user_info["username"]
        user_id = g.user_info["id"]
        target = args
        db = DB()
        status, result = db.select("target", "where data -> '$.target'='%s'" % args["target"])
        if status is True:
            if len(result) == 0:
                # 给用户添加产品线
                info = update_user_product(user_id, args["id"])
                if info["status"] is False:
                    return {"status": False, "message": info["message"]}, 500
                insert_status, insert_result = db.insert("target", json.dumps(target, ensure_ascii=False))
                db.close_mysql()
                if insert_status is not True:
                    logger.error("Add target error: %s" % insert_result)
                    return {"status": False, "message": insert_result}, 500
                audit_log(user, args["id"], "", "target", "add")
            else:
                db.close_mysql()
                return {"status": False, "message": "The target already exists"}, 200
        else:
            db.close_mysql()
            logger.error("Select target error: %s" % result)
            return {"status": False, "message": result}, 500
        return {"status": True, "message": result}, 200


# 上传文件
class UploadTarget(Resource):
    @access_required(role_dict["common_user"])
    def post(self):
        logger.info("UploadTarget")
        args = parser.parse_args()
        host_id = args['host_id']
        file = request.files['file']
        file.save(os.path.join('/tmp', file.filename))
        db = DB()
        try:
            xlsx_file = Xlsx(os.path.join('/tmp', file.filename))
            xlsx_file.read()
            config_db_result = xlsx_file.export_db()
            targets = config_db_result.split(';')
            for target in targets:
                target_dic = eval(target)
                target_dic['host_id'] = host_id
                status, result = db.select("target", "where data -> '$.target'='%s'" % target_dic['target'])
                if status is True:
                    if len(result) == 0:
                        insert_status, insert_result = db.insert("target", json.dumps(target_dic, ensure_ascii=False))
                        if insert_status is not True:
                            return {"status": False, "message": insert_result}, 500
                    else:
                        return {"status": False, "message": "The target already exists"}, 200
                else:
                    return {"status": False, "message": result}, 500
            return {"status": True, "message": ""}, 200
        except Exception as e:
            return {"status": False, "message": str(e)}, 500
        finally:
            db.close_mysql()


class ConfigGenerate(Resource):
    @access_required(role_dict["common_user"])
    def post(self):
        logger.info("ConfigGenerate")
        db = DB()
        # 首先取得所有所需配置参数，并做处理
        args = parser.parse_args()
        host_id = args['host_id']
        key_word = args['key_word']
        path = args['path']
        file_name = args['file_name']
        path_str = str(path)
        if path_str.endswith('/'):
            path_str = path_str
        else:
            path_str = path_str + '/'
        if file_name:
            file_name = file_name
        else:
            file_name = 'snmpconf_' + key_word + '.json'
        state, result = db.select('host', "where data -> '$.id'='%s'" % host_id)
        if state is False:
            return {"status": False, "message": '主机信息未知'}, 500
        host = result[0]
        product_id = host['product_id']
        minion_id = host['minion_id']
        state, result = db.select('product', "where data -> '$.id'='%s'" % product_id)
        product = result[0]
        product_name = product['name']
        master_id = product['salt_master_id']
        logger.info('product_id:'+product_id)
        salt_api = salt_api_for_product(product_id)
        # 完成命令拼装
        command = 'salt-cp ' + minion_id + ' ' + file_name + ' ' + path_str
        logger.info('command:'+command)
        #完成关键词搜索的文件的生成
        status, result = db.select("target", "where data -> '$.host_id'='%s'" % host_id)
        if status is True:
            target_list = result
        else:
            db.close_mysql()
            return {"status": False, "message": result}, 500
        strresult = '[\n'
        for target in target_list:
            model = str(target['model'])
            if model.__contains__(key_word):
                target_str = target.pop('target')
                del target['host_id']
                resdic = {"targets": [target_str], "labels": target}
                strresult += " " + str(resdic) + ',\n'
        strresult = strresult[:-1] + '\n]'
        #结果文件存储，备份
        fo = open(path_str+file_name, "w")
        logger.info('path:'+path_str+file_name)
        fo.write(strresult)
        fo.close()
        #上传文件到gitlab中
        logger.info('222222')
        project, _ = gitlab_project('p-11992012f3fa11ea96120242ac120002', 'state_project')
        # 支持的action create, delete, move, update
        data = {
            'branch': product_name,
            'commit_message': command ,
            'actions': [
                {
                    'action': 'create',
                    'file_path': minion_id+'/'+file_name,
                    'content': strresult
                }
            ]
        }
        if isinstance(project, dict):
            return project, 500
        else:
            try:
                project.commits.create(data)
            except Exception as e:
                return {"status": False, "message": str(e)}, 500
            return {"status": True, "message": ""}, 200
        # 验证权限
        user_info = g.user_info
        if isinstance(salt_api, dict):
            return salt_api, 500
        acl_list = user_info["acl"]
        status = verify_acl(acl_list, command)
        if status["status"]:
            result = salt_api.shell_remote_execution(master_id, command)
            logger.info('result:'+result)
            return {"status": True, "message": result}, 200
