import xlrd, re
from common.log import loggers

logger = loggers()


class Xlsx():
    def __init__(self, xlsx):
        self.data = xlrd.open_workbook(xlsx)
        logger.info("打开成功")
        self.sheet = self.data.sheet_by_index(0)
        self.l = []

    def read(self):
        global l
        for i in range(self.sheet.nrows):
            if i == 0:
                pass
            else:
                self.l.append(self.sheet.row_values(i))
        logger.info("读取信息成功")
        return self.l

    def export(self):
        subdic = {}
        result = []
        strresult = '['

        if self.l:
            for i in self.l:
                dic = {}
                l2 = []
                l2.append(i[3])
                h3c = re.match(r'h3c', i[2], re.I)
                hw = re.match(r'hw', i[2], re.I)
                zte = re.match(r'zte', i[2], re.I)
                if h3c:
                    model = re.sub(h3c.group(0), '华三', i[2])
                elif hw:
                    model = re.sub(hw.group(0), '华为', i[2])
                elif zte:
                    model = re.sub(zte.group(0), '中兴', i[2])
                else:
                    model = i[2]
                subdic["IP"] = i[3]
                subdic["location"] = i[0]
                subdic["model"] = model
                subdic["type"] = i[1]
                dic["targets"] = l2
                dic["labels"] = subdic
                # print(str(dic))
                if i != self.l[-1]:
                    strresult = strresult + str(dic) + ',\n'
                else:
                    strresult = strresult + str(dic) + ']'
                result.append(dic)
        strresult = strresult.replace("'", '"')
        logger.info("返回结果值")
        return strresult

    def export_db(self):
        result = []
        strresult = ''
        if self.l:
            for i in self.l:
                dic = {}
                l2 = []
                l2.append(i[3])
                h3c = re.match(r'h3c', i[2], re.I)
                hw = re.match(r'hw', i[2], re.I)
                zte = re.match(r'zte', i[2], re.I)
                if h3c:
                    model = re.sub(h3c.group(0), '华三', i[2])
                elif hw:
                    model = re.sub(hw.group(0), '华为', i[2])
                elif zte:
                    model = re.sub(zte.group(0), '中兴', i[2])
                else:
                    model = i[2]
                dic['IP'] = i[3]
                dic["location"] = i[0]
                dic["model"] = model
                dic["type"] = i[1]
                dic["target"] = l2
                if i != self.l[-1]:
                    strresult = strresult + str(dic) + ';\n'
                else:
                    strresult = strresult + str(dic)
                result.append(dic)
        logger.info("返回结果值")
        return strresult
