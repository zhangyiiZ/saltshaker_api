# -*- coding:utf-8 -*-
import re

from flask_restful import Resource, reqparse, request
from flask import g
from common.log import loggers
from common.audit_log import audit_log
from common.db import DB
from common.utility import uuid_prefix, salt_api_for_product
from common.sso import access_required
import json

from fileserver.git_fs import get_gitlab
from system.user import update_user_privilege
from common.const import role_dict

logger = loggers()

parser = reqparse.RequestParser()
parser.add_argument("name", type=str, required=True, trim=True)
parser.add_argument("product_id", type=str, required=True, trim=True)
# 不必填写的字段一定要指定默认值为""，否则无法转换成字典
parser.add_argument("gitlab_name", type=str, default="", trim=True)
parser.add_argument("groups", type=str, default=[], action="append")


class Projects(Resource):
    @access_required(role_dict["product"])
    def get(self, project_id):
        db = DB()
        status, result = db.select_by_id("projects", project_id)
        try:
            project_with_group_name = list(transfer_projectGroupID_to_projectGroupNAME(result))[0]
        except Exception as e:
            return {"status": False, "message": str(e)}, 500
        db.close_mysql()
        if status is True:
            if result:
                return {"data": project_with_group_name, "status": True, "message": ""}, 200
            else:
                return {"status": False, "message": "%s does not exist" % project_id}, 404
        else:
            return {"status": False, "message": result}, 500

    @access_required(role_dict["product"])
    def delete(self, project_id):
        db = DB()
        try:
            status, message = update_group_for_delete_project(project_id)
        except Exception as e:
            logger.info('Exception:' + str(e))
        if status is not True:
            return {"status": False, "message": message}, 500
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
        projects = transfer_args_to_project(args)
        db = DB()
        # 判断是否存在
        select_status, select_result = db.select_by_id("projects", project_id)
        if select_status is not True:
            db.close_mysql()
            logger.error("Modify projects error: %s" % select_result)
            return {"status": False, "message": select_result}, 500
        if not select_result:
            db.close_mysql()
            return {"status": False, "message": "%s does not exist" % project_id}, 404
        gitlab_name_origion = select_result['gitlab_name']
        args['gitlab_name'] = gitlab_name_origion
        # 判断名字否已经存在
        status, result = db.select("projects", "where data -> '$.name'='%s' and  data -> '$.product_id'='%s'"
                                   % (args["name"], args["product_id"]))
        if status is True and result:
            if project_id != result[0].get("id"):
                db.close_mysql()
                return {"status": False, "message": "The projects name already exists"}, 200
        try:
            status, message = update_group_for_update_project(project_id, args['groups'], args['name'])
            if status is not True:
                return {"status": False, "message": message}, 500
        except Exception as e:
            return {"status": False, "message": str(e)}, 500
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
        try:
            projects_with_group_name = transfer_projectGroupID_to_projectGroupNAME(projects_with_groupid)
        except Exception as e:
            logger.info('Exception:' + str(e))
            return {"status": False, "message": str(e)}, 500
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
        project = transfer_args_to_project(args)
        # 如果是创建，group们必然是增加此项目名
        status, result = db.select("projects", "where data -> '$.name'='%s' and data -> '$.product_id'='%s'"
                                   % (args["name"], args["product_id"]))
        if status is True:
            if len(result) == 0:
                try:
                    create_git_project(args['product_id'], args['gitlab_name'])
                    git_clone(args['product_id'], args['gitlab_name'])
                except Exception as e:
                    return {"status": False, "message": str(e)}, 500
                insert_status, insert_result = db.insert("projects", json.dumps(project, ensure_ascii=False))
                update_group_for_create_project(project['name'], project['groups'])
                db.close_mysql()
                if insert_status is not True:
                    return {"status": False, "message": insert_result}, 500
                return {"status": True, "message": ""}, 200
            else:
                db.close_mysql()
                return {"status": False, "message": "The projects name already exists"}, 500
        else:
            db.close_mysql()
            return {"status": False, "message": result}, 500


def git_clone(product_id, project_name):
    db = DB()
    status, product = db.select_by_id('product', product_id)
    gitlab_url = product['gitlab_url']
    master = product['salt_master_id']
    gitlab_url = gitlab_url.replace('http://', 'git@')
    gitlab_project_url = re.split(':', gitlab_url)[0] + ':root/'+project_name+'.git'
    #gitlab_project_url = gitlab_url.replace(':80', '/root/') + project_name + '.git'
    command_list = []
    command_list.append('cd /tmp/' + ' \n ')
    command_list.append('git clone '+gitlab_project_url + ' \n ')
    command_final = ''.join(command_list)
    logger.info('command'+command_final)
    salt_api = salt_api_for_product(product_id)
    exec_result = salt_api.shell_remote_execution([master], command_final)



def update_group_for_create_project(project_name, groups_id_list):
    db = DB()
    logger.info('UPDATEGROUP')
    logger.info('project_name:' + project_name + 'groups_id_list:' + str(groups_id_list))
    for group_id in groups_id_list:
        status, group = db.select_by_id('groups', group_id)
        project_name_list = list(group['projects'])
        project_name_list.append(project_name)
        group['projects'] = project_name_list
        status, result = db.update_by_id('groups', json.dumps(group, ensure_ascii=False), group_id)
    db.close_mysql()


def update_group_for_update_project(project_id, new_group_list, project_new_name):
    db = DB()
    status, project = db.select_by_id('projects', project_id)
    project_origion_name = project['name']
    origion_group_list = project['groups']
    common_group_list = [x for x in origion_group_list if x in new_group_list]
    delete_group_list = [x for x in origion_group_list if x not in new_group_list]
    add_group_list = [x for x in new_group_list if x not in origion_group_list]
    status_final = True
    message = ''
    try:
        for group_id in delete_group_list:
            status, group = db.select_by_id('groups', group_id)
            project_list = list(group['projects'])
            project_list.remove(project_origion_name)
            group['projects'] = project_list
            status, result = db.update_by_id('groups', json.dumps(group, ensure_ascii=False), group_id)
            if status is not True:
                status_final = False
                message = 'update error'
        for group_id in add_group_list:
            status, group = db.select_by_id('groups', group_id)
            project_list = list(group['projects'])
            project_list.append(project_new_name)
            group['projects'] = project_list
            status, result = db.update_by_id('groups', json.dumps(group, ensure_ascii=False), group_id)
            if status is not True:
                status_final = False
                message = 'update error'
        if project_origion_name != project_new_name:
            for group_id in common_group_list:
                status, group = db.select_by_id('groups', group_id)
                project_list = list(group['projects'])
                project_list.remove(project_origion_name)
                project_list.append(project_new_name)
                group['projects'] = project_list
                status, result = db.update_by_id('groups', json.dumps(group, ensure_ascii=False), group_id)
                if status is not True:
                    status_final = False
                    message = 'update error'
    except Exception as e:
        status_final = False
        message = str(e)
    logger.info('status_final' + str(status_final))
    return status_final, message


def update_group_for_delete_project(project_id):
    db = DB()
    status, project = db.select_by_id('projects', project_id)
    group_id_list = project['groups']
    project_origion_name = project['name']
    status_final = True
    message = ''
    for group_id in group_id_list:
        status, group = db.select_by_id('groups', group_id)
        project_list = list(group['projects'])
        project_list.remove(project_origion_name)
        group['projects'] = project_list
        status, result = db.update_by_id('groups', json.dumps(group, ensure_ascii=False), group_id)
        if status is not True:
            status_final = False
            message = 'update error'
    return status_final, message


def transfer_args_to_project(args):
    db = DB()
    group_name_list = list(args['groups'])
    group_id_list = []
    for group_name in group_name_list:
        status, result = db.select("groups", "where data -> '$.name'='%s'" % group_name)
        logger.info(str(result[0]['id']))
        group_id_list.append(str(result[0]['id']))
    args['groups'] = group_id_list
    db.close_mysql()
    return args


def transfer_projectGroupID_to_projectGroupNAME(projects_with_groupid):
    db = DB()
    if not isinstance(projects_with_groupid, list):
        projects_with_groupid = [projects_with_groupid]
    projects_with_group_name = []
    for project in projects_with_groupid:
        group_name_list = []
        for group_id in list(project['groups']):
            status, group = db.select_by_id('groups', group_id)
            logger.info('group:' + str(group))
            group_name = group['name']
            group_name_list.append(group_name)
        project['groups'] = group_name_list
        projects_with_group_name.append(project)
    return projects_with_group_name


def create_git_project(product_id, project_name):
    logger.info("create_git_project1")
    db = DB()
    status, result = db.select('projects', "where data -> '$.gitlab_name'='%s'" % project_name)
    if status is True:
        if len(result) == 0:
            logger.info('project_name:' + project_name)
            gl = get_gitlab(product_id)
            try:
                gl.projects.create({'name': project_name})
            except Exception as e:
                raise Exception('该gitlab项目名已被占用')
            projects = gl.projects.list(all=True)
            for pr in projects:
                if str(pr.__dict__.get('_attrs').get('path_with_namespace')).replace('root/', '') == project_name:
                    project = gl.projects.get(pr.__dict__.get('_attrs').get('id'))
                    commit_init_file(project)
            return True
        else:
            db.close_mysql()
            return False
    else:
        db.close_mysql()
        raise Exception('mysql select from projects error')


def commit_init_file(project):
    branch_name = "master"
    data_create = {
        'branch': branch_name,
        'commit_message': 'init',
        'actions': [
            {
                'action': "create",
                'file_path': '/' + 'README',
                'content': 'README'
            }
        ]
    }
    if isinstance(project, dict):
        return False
    else:
        project.commits.create(data_create)
        return True
