# -*- coding:utf-8 -*-
import os

from flask_restful import Resource, reqparse, request
from flask import g, app
from common.log import loggers
from common.audit_log import audit_log
from common.db import DB
from common.utility import uuid_prefix
from common.sso import access_required
import json

from common.xlsx import Xlsx
from fileserver.git_fs import gitlab_project
from system.user import update_user_privilege, update_user_product
from common.const import role_dict
from fileserver.rsync_fs import rsync_config
from common.saltstack_api import SaltAPI
import gitlab

logger = loggers()

parser = reqparse.RequestParser()
parser.add_argument("host_id", type=str, required=True, trim=True)
parser.add_argument("target", type=str, required=True, trim=True)
parser.add_argument("IP", type=str, required=True, trim=True)
parser.add_argument("location", type=str, required=True, trim=True)
parser.add_argument("model", type=str, required=True, trim=True)
parser.add_argument("type", type=str, required=True, trim=True)
parser.add_argument("project", type=str, required=True, trim=True)
parser.add_argument("client", type=str, required=True, trim=True)
parser.add_argument("pool", type=str, required=True, trim=True)


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
        db = DB()
        user_info = g.user_info
        role_sql = []
        if user_info["role"]:
            for role in user_info["role"]:
                role_sql.append("data -> '$.id'='%s'" % role)
            sql = " or ".join(role_sql)
            role_status, role_result = db.select("role", "where %s" % sql)
            if role_status and role_result:
                for role in role_result:
                    if role["tag"] == 0:
                        status, result = db.select("target", "")
                        db.close_mysql()
                        target_list = []
                        if status is True:
                            if result:
                                target_list = result
                        else:
                            return {"status": False, "message": result}, 500
                        return {"data": target_list, "status": True, "message": ""}, 200

        sql_list = []
        target_list = []
        if user_info["product"]:
            for target in user_info["product"]:
                sql_list.append("data -> '$.id'='%s'" % target)
            sql = " or ".join(sql_list)
            status, result = db.select("target", "where %s" % sql)
            db.close_mysql()
            if status is True:
                if result:
                    target_list = result
                    return {"data": target_list, "status": True, "message": ""}, 200
                else:
                    return {"status": False, "message": "Group does not exist"}, 404
            else:
                return {"status": False, "message": result}, 500
        return {"data": target_list, "status": True, "message": ""}, 200

    @access_required(role_dict["product"])
    def post(self):
        args = parser.parse_args()
        args["id"] = uuid_prefix("p")
        user = g.user_info["username"]
        user_id = g.user_info["id"]
        target = args
        db = DB()
        status, result = db.select("target", "where data -> '$.name'='%s'" % args["target"])
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
        file = request.files['file']
        file.save(os.path.join('/tmp', file.filename))
        db = DB()
        try:
            xlsx_file = Xlsx(os.path.join('/tmp', file.filename))
            xlsx_file.read()
            config_db_result = xlsx_file.export_db()
            targets = config_db_result.split(';')
            for target in targets:
                status, result = db.select("target", "where data -> '$.name'='%s'" % target)
                if status is True:
                    if len(result) == 0:
                        insert_status, insert_result = db.insert("target", target)
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







