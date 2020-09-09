import xlrd, re
from common.log import loggers

logger = loggers()


class Xlsx():
    def __init__(self, xlsx):
        self.data = xlrd.open_workbook(xlsx)
        self.sheet = self.data.sheet_by_index(0)
        self.l = []
        self.la = []

    def read(self):  # 读取excel放到列表里
        global l

        for i in range(self.sheet.nrows):
            if i == 0:
                self.la = self.sheet.row_values(i)
                print(self.la)
            else:

                self.l.append(self.sheet.row_values(i))  # 把第i行的数据放到列表第i个
        return self.l

    def export(self):
        subdic = {}
        result = []
        strresult = "["
        in_ip = ""
        for i in range(len(self.la)):

            if self.la[i] == "IP":
                in_ip = i
        if not in_ip:
            return "没有找到IP这一列"

        strresult2 = '[\n'
        if self.l:
            for i in self.l:
                dic = {}
                l2 = []
                l2.append(i[3])
                cont = {}
                for j in range(len(self.la)):
                    cont[self.la[j]] = i[j]
                resdic = {"targets": [i[in_ip]], "labels": cont}
                print(resdic)
                if i != self.l[-1]:
                    strresult2 += " " + str(resdic) + ',\n'
                else:
                    strresult2 += " " + str(resdic) + "\n]"
        return strresult2.replace("'", '"')

    def export_db(self):
        in_ip = ""
        for i in range(len(self.la)):
            if self.la[i] == "IP":
                in_ip = i
        if not in_ip:
            return "没有找到IP这一列"
        strresult = ''
        if self.l:
            for i in self.l:
                dic = {}
                l2 = []
                l2.append(i[3])
                cont = {}
                for j in range(len(self.la)):
                    cont[self.la[j]] = i[j]
                cont['target'] = i[in_ip]
                print(cont)
                if i != self.l[-1]:
                    strresult += str(cont) + ';\n'
                else:
                    strresult += str(cont)
        return strresult
