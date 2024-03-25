from __future__ import (absolute_import, division, print_function,
                        unicode_literals)

import datetime  # For datetime objects
import os.path  # To manage paths
import sys,time  # To find out the script name (in argv[0])


# Import the backtrader platform
import backtrader as bt
from load_binance_csv import BINACSVData

class TradeResult():
    def __init__(self) -> None:
        self.times = 0

# Create a Stratey
class TestStrategy(bt.Strategy):
    params = (
        ('maperiod', 15),
        ('printlog', False),
    )

    def log(self, txt, dt=None, doprint=False):
        ''' Logging function fot this strategy'''
        if self.params.printlog or doprint:
            dt = dt or self.datas[0].datetime.date(0)
            print('%s, %s' % (dt.isoformat(), txt))

    def __init__(self):
        # Keep a reference to the "close" line in the data[0] dataseries
        self.dataclose = self.datas[0].close
        self.datahigh = self.datas[0].high
        self.datalow = self.datas[0].low

        #result
        self.result = TradeResult()

        # To keep track of pending orders and buy price/commission
        self.order = None
        self.buyprice = None
        self.buycomm = None
        self.data_offset = 0
        self.order_high_price = None

        # Add a MovingAverageSimple indicator
        self.sma_short = bt.indicators.SimpleMovingAverage(
            self.datas[0], period=7)

        self.sma_middle = bt.indicators.SimpleMovingAverage(
            self.datas[0], period=25)
        
        self.sma_long = bt.indicators.SimpleMovingAverage(
            self.datas[0], period=99)
        
    def notify_order(self, order):
        if order.status in [order.Submitted, order.Accepted]:
            # Buy/Sell order submitted/accepted to/by broker - Nothing to do
            return

        # Check if an order has been completed
        # Attention: broker could reject order if not enough cash
        if order.status in [order.Completed]:
            if order.isbuy():
                self.log(
                    'BUY EXECUTED, Price: %.2f, Cost: %.2f, Comm %.2f' %
                    (order.executed.price,
                     order.executed.value,
                     order.executed.comm))

                self.order_high_price = self.dataclose[0]
                self.buyprice = order.executed.price
                self.buycomm = order.executed.comm
            else:  # Sell
                self.log('SELL EXECUTED, Price: %.2f, Cost: %.2f, Comm %.2f' %
                         (order.executed.price,
                          order.executed.value,
                          order.executed.comm))

            self.bar_executed = len(self)

        elif order.status in [order.Canceled, order.Margin, order.Rejected]:
            self.log('Order Canceled/Margin/Rejected')

        # Write down: no pending order
        self.order = None

    def notify_trade(self, trade):
        if not trade.isclosed:
            return

        self.log('OPERATION PROFIT, GROSS %.2f, NET %.2f' %
                 (trade.pnl, trade.pnlcomm))

    def next(self): #begin from all sma is valid!
        # Simply log the closing price of the series from the reference
        # self.log('Close, %.2f' % self.dataclose[0])
        self.data_offset = self.data_offset + 1
        # print(len(self.sma_short))
        # for i in range(0,len(self.sma_short)):
        #     print((self.sma_short[i]))
        # print(len(self.sma_middle))
        # for i in range(0,len(self.sma_middle)):
        #     print((self.sma_middle[i]))
        # print(len(self.sma_long))
        # for i in range(0,len(self.sma_long)):
        #     print((self.sma_long[i]))
        # Check if an order is pending ... if yes, we cannot send a 2nd one
        if self.order:
            return

        # Check if we are in the market
        if not self.position:

            # Not yet ... we MIGHT BUY if ...
            # print(self.dataclose[0],self.sma_short[0])
            if self.sma_short[0] > self.sma_short[-1] and self.sma_short[-1] > self.sma_short[-2] and  self.sma_short[-2] > self.sma_short[-3] \
                and self.sma_middle[0] > self.sma_middle[-1] \
                and self.dataclose[0] > self.sma_short[0]:

                # BUY, BUY, BUY!!! (with all possible default parameters)
                self.log('BUY CREATE, %.2f' % self.dataclose[0])

                # Keep track of the created order to avoid a 2nd order
                self.order = self.buy(size=0.01)
                self.order_high_price = self.dataclose[0]
                self.result.times = self.result.times + 1

        else:
            if self.datahigh[0] > self.order_high_price:
                self.order_high_price = self.datahigh[0]

            if (self.order_high_price -self.buyprice)/self.buyprice < 0.003: #0.3%
                self.log('ignore small change !, %.2f' % self.dataclose[0])
            elif self.datalow[0] < ((self.order_high_price -self.buyprice)*0.618 + self.buyprice):
                # SELL, SELL, SELL!!! (with all possible default parameters)
                self.log('SELL CREATE, %.2f' % self.dataclose[0])

                # Keep track of the created order to avoid a 2nd order
                self.order = self.sell(size=0.01)

    def stop(self):
        self.log("trade times :%d "%self.result.times)
        self.log('(MA Period %2d) Ending Value %.2f' %
                 (self.params.maperiod, self.broker.getvalue()), doprint=True)


    # def judge_up(self,sma):
    #     if len(sma) < 3:
    #         return False
    #     if sma[0] > sma[-1] and sma[-1] > sma[-2] 

if __name__ == '__main__':
    currentDateAndTime = time.localtime()
    print(currentDateAndTime)
    # Create a cerebro entity
    cerebro = bt.Cerebro()

    # Add a strategy
    strats = cerebro.optstrategy(
        TestStrategy,
        maperiod=10,
        printlog=True)

    # Datas are in a subfolder of the samples. Need to find where the script is
    # because it could have been called from anywhere
    modpath = os.path.dirname(os.path.abspath(sys.argv[0]))

    datapath = os.path.join(modpath, '..','datas','klines1m.csv')
    # Create a Data Feed
    data = BINACSVData(
        dataname=datapath,
        # Do not pass values before this date
        fromdate=datetime.datetime(1990, 1, 1),
        # Do not pass values before this date
        todate=datetime.datetime(2024, 3, 24),
        nullvalue=0.0,

        datetime=0,
        high=2,
        low=3,
        open=1,
        close=4,
        volume=5,
        reverse=True,
        printlog=True
    )

    # Add the Data Feed to Cerebro
    cerebro.adddata(data)

    # Set our desired cash start
    cerebro.broker.setcash(1000.0)

    # Add a FixedSize sizer according to the stake
    cerebro.addsizer(bt.sizers.FixedSize, stake=1)

    # Set the commission
    cerebro.broker.setcommission(commission=0.001)

    # Run over everything
    cerebro.run(maxcpus=1)