# -*- coding:utf-8 -*-
from flask_restful import Resource, reqparse, request
from flask import g
from common.log import loggers
from common.audit_log import audit_log
from common.db import DB
from common.utility import uuid_prefix
from common.sso import access_required
import json
from system.user import update_user_privilege
from common.const import role_dict

logger = loggers()

parser = reqparse.RequestParser()
parser.add_argument("name", type=str, required=True, trim=True)
parser.add_argument("product_id", type=str, required=True, trim=True)
# 不必填写的字段一定要指定默认值为""，否则无法转换成字典
parser.add_argument("gitlab_name", type=str, default="", trim=True)
parser.add_argument("group", type=str, default=[], action="append")


class Projects(Resource):
    @access_required(role_dict["product"])
    def get(self, project_id):
        db = DB()
        status, result = db.select_by_id("projects", project_id)
        db.close_mysql()
        if status is True:
            if result:
                return {"data": result, "status": True, "message": ""}, 200
            else:
                return {"status": False, "message": "%s does not exist" % project_id}, 404
        else:
            return {"status": False, "message": result}, 500

    @access_required(role_dict["product"])
    def delete(self, project_id):
        db = DB()
        status, result = db.delete_by_id("projects", project_id)
        db.close_mysql()
        if status is not True:
            logger.error("Delete projects error: %s" % result)
            return {"status": False, "message": result}, 500
        if result is 0:
            return {"status": False, "message": "%s does not exist" % project_id}, 404
        return {"status": True, "message": ""}, 200

    @access_required(role_dict["product"])
    def put(self, project_id):
        args = parser.parse_args()
        args["id"] = project_id
        projects = args
        db = DB()
        # 判断产品线是否存在
        status, result = db.select_by_id("product", args["product_id"])
        if status is True:
            if not result:
                db.close_mysql()
                return {"status": False, "message": "%s does not exist" % args["product_id"]}, 404
        else:
            return {"status": False, "message": result}, 500
        # 判断是否存在
        select_status, select_result = db.select_by_id("projects", project_id)
        if select_status is not True:
            db.close_mysql()
            logger.error("Modify projects error: %s" % select_result)
            return {"status": False, "message": select_result}, 500
        if not select_result:
            db.close_mysql()
            return {"status": False, "message": "%s does not exist" % project_id}, 404
        # 判断名字否已经存在
        status, result = db.select("projects", "where data -> '$.name'='%s' and  data -> '$.product_id'='%s'"
                                   % (args["name"], args["product_id"]))
        if status is True and result:
            if project_id != result[0].get("id"):
                db.close_mysql()
                return {"status": False, "message": "The projects name already exists"}, 200
        status, result = db.update_by_id("projects", json.dumps(projects, ensure_ascii=False), project_id)
        db.close_mysql()
        if status is not True:
            logger.error("Modify projects error: %s" % result)
            return {"status": False, "message": result}, 500
        return {"status": True, "message": ""}, 200


class ProjectsList(Resource):
    @access_required(role_dict["product"])
    def get(self):
        # product_id = request.args.get("product_id")
        db = DB()
        status, projects_with_groupid = db.select("projects", '')
        projects_with_group_name = []
        for project in projects_with_groupid:
            group_name_list = []
            for group_id in list(project['group']):
                status, group = db.select_by_id('groups', group_id)
                group_name = group['name']
                group_name_list.append(group_name)
            project['group'] = group_name_list
            projects_with_group_name.append(project)
        db.close_mysql()
        if status is True:
            return {"data": projects_with_group_name, "status": True, "message": ""}, 200
        else:
            return {"status": False, "message": projects_with_group_name}, 500

    @access_required(role_dict["product"])
    def post(self):
        args = parser.parse_args()
        args["id"] = uuid_prefix("project")
        db = DB()
        group_name_list = list(args['group'])
        group_id_list = []
        for group_name in group_name_list:
            status, result = db.select("groups", "where data -> '$.name'='%s'" % group_name)
            group_id_list.append(str(result[0]['id']))
        args['group'] = group_id_list
        projects = args
        status, result = db.select_by_id("product", args["product_id"])
        if status is True:
            if not result:
                db.close_mysql()
                return {"status": False, "message": "%s does not exist" % args["product_id"]}, 404
        else:
            return {"status": False, "message": result}, 500
        status, result = db.select("projects", "where data -> '$.name'='%s' and data -> '$.product_id'='%s'"
                                   % (args["name"], args["product_id"]))
        if status is True:
            if len(result) == 0:
                insert_status, insert_result = db.insert("projects", json.dumps(projects, ensure_ascii=False))
                db.close_mysql()
                if insert_status is not True:
                    logger.error("Add projects error: %s" % insert_result)
                    return {"status": False, "message": insert_result}, 500
                return {"status": True, "message": ""}, 201
            else:
                db.close_mysql()
                return {"status": False, "message": "The projects name already exists"}, 200
        else:
            db.close_mysql()
            logger.error("Select projects name error: %s" % result)
            return {"status": False, "message": result}, 500
