import itertools,time
...
import backtrader as bt
from datetime import datetime
from backtrader import date2num
import collections, io

class BINACSVData(bt.CSVDataBase):

    params = (
        ('reverse', False),
        ('adjclose', True),
        ('adjvolume', True),
        ('round', True),
        ('decimals', 2),
        ('roundvolume', False),
        ('swapcloses', False),
    )

    def start(self):
        # Nothing to do for this data feed type
        super(BINACSVData, self).start()
        if not self.params.reverse:
            return
        # Yahoo sends data in reverse order and the file is still unreversed
        dq = collections.deque()
        for line in self.f:
            dq.appendleft(line)

        print("BINACSVData data num:%d"%len(dq))
        f = io.StringIO(newline=None)
        f.writelines(dq)
        f.seek(0)
        self.f.close()
        self.f = f

    def stop(self):
        # Nothing to do for this data feed type
        super(BINACSVData, self).stop()
        pass

    def _loadline(self, linetokens):
        i = itertools.count(0)

        dttxt = linetokens[next(i)]
        dt = datetime.fromtimestamp(int(dttxt) / 1000.0)
        dtnum = date2num(dt)
        self.lines.datetime[0] = dtnum
        self.lines.open[0] = float(linetokens[next(i)])
        self.lines.high[0] = float(linetokens[next(i)])
        self.lines.low[0] = float(linetokens[next(i)])
        self.lines.close[0] = float(linetokens[next(i)])
        self.lines.volume[0] = float(linetokens[next(i)])
        self.lines.openinterest[0] = -1

        return True