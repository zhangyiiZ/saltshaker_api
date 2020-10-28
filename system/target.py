# -*- coding:utf-8 -*-
import os
from concurrent.futures.thread import ThreadPoolExecutor

from flask_restful import Resource, reqparse, request
from flask import g, app
from common.log import loggers
from common.audit_log import audit_log
from common.db import DB
from common.utility import uuid_prefix, salt_api_for_product
from common.sso import access_required
import json
from common.xlsx import Xlsx
from fileserver.git_fs import gitlab_project, gitlab_project_name
from system.user import update_user_privilege, update_user_product
from common.const import role_dict
from fileserver.rsync_fs import rsync_config

logger = loggers()

parser = reqparse.RequestParser()
parser.add_argument("host_id", type=str, required=True, trim=True)
parser.add_argument("target_id", type=str, default='', trim=True)
parser.add_argument("target", type=str, default='', trim=True)
parser.add_argument("IP", type=str, default='', trim=True)
parser.add_argument("location", type=str, default='', trim=True)
parser.add_argument("model", type=str, default='', trim=True)
parser.add_argument("type", type=str, default='', trim=True)
parser.add_argument("project", type=str, default='', trim=True)
parser.add_argument("client", type=str, default='', trim=True)
parser.add_argument("pool", type=str, default='', trim=True)
parser.add_argument("path", type=str, default='', trim=True)
parser.add_argument("key_word", type=str, default='', trim=True)
parser.add_argument("file_name", type=str, default='', trim=True)
parser.add_argument("cipher", type=str, default='', trim=True)


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
        db = DB()
        status, result = db.delete_by_id("target", target_id)
        db.close_mysql()
        logger.info('delete:' + str(result))
        if status is not True:
            logger.error("Delete product error: %s" % result)
            return {"status": False, "message": result}, 500
        if result is 0:
            return {"status": False, "message": "%s does not exist" % target_id}, 404
        return {"status": True, "message": ""}, 200

    @access_required(role_dict["product"])
    def put(self, target_id):
        args = parser.parse_args()
        logger.info(args['host_id'])
        args["id"] = target_id
        logger.info('id:' + target_id)
        del args['path'], args['key_word'], args['file_name'], args['target_id'], args['cipher']
        target = args
        db = DB()
        status, result = db.select_by_id('target', target_id)
        origion_IP = result['IP']
        if origion_IP != args['IP']:
            status, message = judge_target_IP_exist(args['IP'], args['host_id'])
            if status is not True:
                return {"status": False, "message": message}, 500
        status, result = db.update_by_id("target", json.dumps(target, ensure_ascii=False), target_id)
        db.close_mysql()
        if status is not True:
            logger.error("Modify target: %s" % result)
            return {"status": False, "message": result}, 500
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
        args["id"] = uuid_prefix("t")
        del args['path'], args['key_word'], args['file_name'], args['target_id'], args['cipher']
        target = args
        db = DB()
        status, message = judge_target_IP_exist(args['IP'], args['host_id'])
        if status is True:
            insert_status, insert_result = db.insert("target", json.dumps(target, ensure_ascii=False))
            if insert_status is not True:
                db.close_mysql()
                return {"status": False, "message": str(insert_result)}, 500
        else:
            db.close_mysql()
            return {"status": False, "message": message}, 500
        db.close_mysql()
        return {"status": True, "message": message}, 200


def judge_target_IP_exist(IP, host_id):
    db = DB()
    status, result = db.select("target", "where data -> '$.IP'='%s' AND data -> '$.host_id'='%s'" % (
        IP, host_id))
    if status is not True:
        return False, 'select error'
    else:
        if len(result) == 0:
            return True, ''
        else:
            return False, 'IP already exists'


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
            status, set_repeat = self.get_repeat_target(targets)
            if not status:
                logger.info('存在重复IP')
                return {"status": True, "message": "存在重复IP！为：" + str(set_repeat)}, 200
            exist_ip_list = []
            for i in range(0, len(targets) - 1):
                target_dic = eval(targets[i])
                target_dic['host_id'] = host_id
                target_dic['id'] = uuid_prefix('t')
                logger.info(str(target_dic))
                status, message = judge_target_IP_exist(target_dic['IP'], host_id)
                if status:
                    insert_status, insert_result = db.insert("target", json.dumps(target_dic, ensure_ascii=False))
                    if insert_status is not True:
                        logger.error("error:" + insert_result)
                        return {"status": False, "message": str(insert_result)}, 200
                else:
                    exist_ip_list.append(target_dic['IP'])
            if len(exist_ip_list) == 0:
                return {"status": True, "message": ""}, 200
            else:
                return {"status": False, "message": "表格中有已经存在的IP：" + str(exist_ip_list) + ',其余IP已经添加完成'}, 200
        except Exception as e:
            logger.info('error:' + str(e))
            return {"status": False, "message": str(e)}, 200
        finally:
            logger.info("close db")
            db.close_mysql()

    def get_repeat_target(self, target_list):
        set_base = set()
        set_repeat = set()
        for i in range(0, len(target_list) - 1):
            target_dic = eval(target_list[i])
            key = target_dic['IP']
            if set_base.__contains__(key):
                set_repeat.add(key)
            else:
                set_base.add(key)
        if set_repeat:
            return False, set_repeat
        else:
            return True, set_repeat


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
        if path_str:
            if path_str.endswith('/'):
                path_str = path_str
            else:
                path_str = path_str + '/'
        else:
            path_str = '/usr/local/prometheus/conf.d/'
        if file_name:
            file_name = file_name
        else:
            file_name = 'snmpconf_' + key_word + '.json'
        state, result = db.select('host', "where data -> '$.id'='%s'" % host_id)
        if state is False:
            return {"status": False, "message": '主机信息未知'}, 500
        host = dict(result[0])
        product_id = host['product_id']
        minion_id = host['minion_id']
        state, product_result = db.select('product', "where data -> '$.id'='%s'" % product_id)
        if state is False:
            return {"status": False, "message": 'product未知'}, 500
        product_host = product_result[0]
        master_id = product_host['salt_master_id']
        salt_api = salt_api_for_product(product_id)
        # 完成关键词搜索的文件的生成
        status, result = db.select("target", "where data -> '$.host_id'='%s'" % host_id)
        if status is True:
            target_list = result
        else:
            db.close_mysql()
            return {"status": False, "message": result}, 500
        try:
            strresult = '[\n'
            for target in target_list:
                model = str(target['model'])
                if model.__contains__(key_word):
                    target_str = target.pop('target')
                    del target['host_id'], target['id']
                    resdic = {"targets": [target_str], "labels": target}
                    strresult += " " + str(resdic) + ',\n'
            strresult = strresult[:-1] + '\n]'
        except Exception as e:
            return {"status": False, "message": '监控目标信息解析出错'}, 500

        # 上传文件到gitlab中
        project_name_list = list(get_host_project(host))
        logger.info('project_name_list' + str(project_name_list))
        if len(project_name_list) == 0:
            return {"status": False, "message": '该主机无归属项目'}, 200
        elif len(project_name_list) > 1:
            return {"status": False, "message": '该主机所属项目不唯一！' + str(project_name_list)}, 200
        state, result = db.select('projects', "where data -> '$.name'='%s'" % project_name_list[0])
        project_gitlab_name = result[0]['gitlab_name']
        logger.info("project_gitlab_name:" + project_gitlab_name)
        project, _ = gitlab_project_name(product_id, project_gitlab_name)
        # 完成命令拼装
        source = '/tmp/' + project_gitlab_name + '/' + minion_id + '/' + file_name
        source_tmp = '/tmp/' + project_gitlab_name + '/' + minion_id + '/tmp_file'
        dest = path_str + file_name
        command = 'salt-cp ' + minion_id + ' ' + source_tmp + ' ' + dest
        # 支持的action create, delete, move, update
        branch_name = "master"
        data_create = {
            'branch': branch_name,
            'commit_message': command,
            'actions': [
                {
                    'action': "create",
                    'file_path': minion_id + '/' + file_name,
                    'content': strresult
                }
            ]
        }
        data_update = {
            'branch': branch_name,
            'commit_message': command,
            'actions': [
                {
                    'action': "update",
                    'file_path': minion_id + '/' + file_name,
                    'content': strresult
                }
            ]
        }
        if isinstance(project, dict):
            return project, 500
        else:
            try:
                project.commits.create(data_create)
            except Exception as e:
                # logger.info('update'+str(e))
                project.commits.create(data_update)
            # 验证权限,执行发送功能
        command_path = 'mkdir -p ' + path_str
        logger.info('minion_id:' + minion_id)
        salt_api.shell_remote_execution(minion_id, command_path)
        # 因为传输中名称需要中文，故使用中间文件
        command_list = []
        command_list.append('cd /tmp/' + project_gitlab_name + ' \n ')
        command_list.append('git pull \n ')
        command_list.append('cp ' + source + ' ' + source_tmp + ' \n ')
        command_list.append(command + ' \n ')
        command_list.append('rm -f ' + source_tmp + ' \n ')
        command_final = ''.join(command_list)
        logger.info('command:' + command_final)
        result = salt_api.shell_remote_execution([master_id], command_final)
        logger.info('result:' + str(result))
        if str(result).__contains__('True'):
            return {"status": True, "message": '配置发送成功'}, 200
        else:
            return {"status": False, "message": '配置发送失败:' + str(result)}, 500


def get_host_project(host):
    minion_id = host['minion_id']
    db = DB()
    status, group_list = db.select('groups', '')
    project_name_list = []
    try:
        for group in group_list:
            minion_list = list(group['minion'])
            if minion_list.__contains__(minion_id):
                project_name_list = project_name_list + group['projects']
    except Exception as e:
        logger.info('Exception:' + str(e))
    db.close_mysql()
    return project_name_list


class PingList(Resource):
    @access_required(role_dict["common_user"])
    def post(self):
        logger.info("PingList")
        args = parser.parse_args()
        db = DB()
        host_id = args['host_id']
        cipher = args['cipher']
        state, result = db.select('host', "where data -> '$.id'='%s'" % host_id)
        minion_id = result[0]['minion_id']
        logger.info('minion_id:' + minion_id)
        product_id = result[0]['product_id']
        salt_api = salt_api_for_product(product_id)
        state, targets = db.select('target', "where data -> '$.host_id'='%s'" % host_id)
        targets_not = []
        thread_pool = ThreadPoolExecutor(max_workers=10, thread_name_prefix="target_")
        futures = []
        for target in targets:
            future = thread_pool.submit(pingTarget, target, minion_id, salt_api, cipher)
            futures.append(future)
        thread_pool.shutdown(wait=True)
        for future in futures:
            result = future.result()
            logger.info(str(result['status']))
            if str(result['status']).__contains__("Timeout") | str(result['status']).__contains__("Unknown"):
                targets_not.append(result["target"])
        return {"status": True, "message": '配置发送成功', "data": targets_not}, 200


def pingTarget(target, minion_id, salt_api, cipher):
    command = 'snmpwalk -v 2c -t 0.5 -c \'' + cipher + '\' ' + target["IP"] + ' 1.3.6.1.2.1.1.1'
    logger.info(command)
    exec_result = salt_api.shell_remote_execution([minion_id], command)
    result = {'target': target, 'status': exec_result}
    return result


class SinglePing(Resource):
    @access_required(role_dict["common_user"])
    def post(self):
        logger.info("SinglePing")
        args = parser.parse_args()
        target_id = args['target_id']
        # 获得所需参数minion_id、product_id、target_ip
        db = DB()
        state, result = db.select_by_id('target', target_id)
        target_ip = result['IP']
        host_id = result['host_id']
        state, result = db.select_by_id('host', host_id)
        minion_id = result['minion_id']
        product_id = result['product_id']
        salt_api = salt_api_for_product(product_id)
        command = 'snmpwalk -v 2c -c \'yundiao*&COC2016\' ' + target_ip + ' 1.3.6.1.2.1.1.1'
        sysDescr = salt_api.shell_remote_execution([minion_id], command)

        response_data = {}
        if str(sysDescr[minion_id]).__contains__("Timeout") | str(sysDescr[minion_id]).__contains__("Unknown"):
            response_data['status'] = '设备网络不通'
        else:
            response_data['status'] = "设备正常"
        response_data['sysDescr'] = str(sysDescr[minion_id])
        return {"status": True, "message": '成功', "data": response_data}, 200


class TruncateTarget(Resource):
    @access_required(role_dict["common_user"])
    def post(self):
        logger.info("TruncateTarget")
        args = parser.parse_args()
        host_id = args['host_id']
        db = DB()
        state, result = db.delete('target', "where data -> '$.host_id'='%s'" % host_id)
        if state:
            return {"status": True, "message": '成功'}, 200
        else:
            return {"status": False, "message": '删除失败'}, 500
