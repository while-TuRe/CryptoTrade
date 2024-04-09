from __future__ import (absolute_import, division, print_function,
                        unicode_literals)

import datetime  # For datetime objects
import os.path  # To manage paths
import sys,time  # To find out the script name (in argv[0])
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
from sklearn import linear_model

# Import the backtrader platform
import backtrader as bt

from load_binance_csv import BINACSVData
import btc_enum


class TradeResult():
    def __init__(self) -> None:
        self.times = 0

class MvDirection():
    Unknown = 0
    Up = 1
    Down = 2

_cash = 10000
_key_point_width=300

# Create a Stratey
class TestStrategy(bt.Strategy):
    params = (
        ('maperiod', 15),
        ('user_scope', btc_enum.Scope.BUY),  #0:buy,1:sell,2:all
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
        self.dataopen = self.datas[0].open
        self.datahigh = self.datas[0].high
        self.datalow = self.datas[0].low
        self.volume = self.datas[0].volume
        self.user_position = btc_enum.Position.Free  #1:short,2:long
        #result
        self.result = TradeResult()

        # To keep track of pending orders and buy price/commission
        self.order = None
        self.buyprice = None
        self.sellprice = None
        self.buycomm = None
        self.data_offset = 0
        self.order_high_price = None
        self.order_low_price = None
        self.short_make_times = 0
        self.short_wrong_times = 0
        self.long_make_times = 0
        self.long_wrong_times = 0
        # self.data_analyze()
        # Add a MovingAverageSimple indicator
        self.sma_short = bt.indicators.SimpleMovingAverage(
            self.datas[0], period=7)

        self.sma_middle = bt.indicators.SimpleMovingAverage(
            self.datas[0], period=25)
        
        self.sma_long = bt.indicators.SimpleMovingAverage(
            self.datas[0], period=99)

        self.smasig = bt.ind.CrossOver(self.sma_short, self.sma_middle)

        macd = bt.ind.MACD(self.datas[0],
                           period_me1=25,
                           period_me2=99,
                           period_signal=2)

        # Cross of macd.macd and macd.signal
        self.macdsig = bt.ind.CrossOver(macd.macd, macd.signal)

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
                if self.user_position == btc_enum.Position.Short:
                    if self.sellprice > self.buyprice:
                        self.short_make_times = self.short_make_times + 1
                    else: self.short_wrong_times = self.short_wrong_times+1
            else:  # Sell
                self.log('SELL EXECUTED, Price: %.2f, Cost: %.2f, Comm %.2f' %
                         (order.executed.price,
                          order.executed.value,
                          order.executed.comm))
                self.order_low_price = self.dataclose[0]
                self.sellprice = order.executed.price
                if self.user_position == btc_enum.Position.Long:
                    if self.sellprice < self.buyprice:
                        self.long_make_times = self.long_make_times + 1
                    else: self.long_wrong_times = self.long_wrong_times+1

            self.bar_executed = len(self)

        elif order.status in [order.Canceled, order.Margin, order.Rejected]:
            self.log('Order Canceled/Margin/Rejected')
            self.quit()

        # Write down: no pending order
        self.order = None

    def notify_trade(self, trade):
        if not trade.isclosed:
            return
        self.log('OPERATION PROFIT, GROSS %.2f, NET %.2f' %
                 (trade.pnl, trade.pnlcomm))
        if self.broker.getvalue() < _cash*0.5:
            self.log("We Are Broken !!!")
            self.quit()

    def next(self): #begin from all sma is valid!
        # Simply log the closing price of the series from the reference
        # self.log('Close, %.2f' % self.dataclose[0])
        self.data_offset = self.data_offset + 1
        if self.order:
            return
        # Check if we are in the market
        if not self.position:
            if self.params.user_scope in [btc_enum.Scope.BUY,btc_enum.Scope.ALL]:
                # Not yet ... we MIGHT BUY if ...
                # print(self.dataclose[0],self.sma_short[0])
                if self.smasig[0] > 0.0 and \
                    self.sma_middle[0] < self.sma_middle[-1]:

                    # BUY, BUY, BUY!!! (with all possible default parameters)
                    self.log('BUY CREATE, %.2f' % self.dataclose[0])

                    # Keep track of the created order to avoid a 2nd order
                    self.order = self.buy(size=self.order_size())
                    self.order_high_price = self.dataclose[0]
                    self.result.times = self.result.times + 1
                    self.user_position = btc_enum.Position.Long
            elif self.params.user_scope in [btc_enum.Scope.SELL,btc_enum.Scope.ALL]:
                if self.smasig[0] < 0.0 :
                    s_perid_a,b=self.linear_fitting(self.dataclose,7)
                    m_perid_a,b=self.linear_fitting(self.dataclose,25)
                    high_a,high_b=self.linear_fitting(self.datahigh,7)
                    low_a,low_b=self.linear_fitting(self.datalow,7)
                    average=self.average_range(25)
                    # print("a:{},average_range:{}".format(s_perid_a,average))
                    # if m_perid_a - s_perid_a >average*0.5 \
                    #     and high_a<=0 and low_a<0:
                    if m_perid_a < 0 and high_a<0 and low_a<0\
                        and self.average_volume(3) < self.average_volume(99)*3 \
                        and self.average_volume(3) > self.average_volume(99)*1.3 \
                        and abs(m_perid_a) > average*0.029:
                        # and m_perid_a - s_perid_a >average*0.1 \
                        self.sell(size=self.order_size())
                        # BUY, BUY, BUY!!! (with all possible default parameters)
                        self.log('SELL CREATE, %.2f' % self.dataclose[0])

                        # Keep track of the created order to avoid a 2nd order
                        self.order_low_price = self.dataclose[0]
                        self.result.times = self.result.times + 1
                        self.user_position = btc_enum.Position.Short
        else:   #in market
            if self.user_position ==btc_enum.Position.Long:#Long(做多)
                if self.smasig[0] < 0.0:

                    # Keep track of the created order to avoid a 2nd order
                    self.order = self.close()
                # if self.datahigh[0] > self.order_high_price:
                #     self.order_high_price = self.datahigh[0]

                # if self.dataclose[0] < self.buyprice:
                #     if (self.buyprice - self.dataclose[0]) > 0.003: #0.3%  we are losing!!!!
                #         self.close()
                # elif abs(self.dataclose[0] - self.buyprice)/self.buyprice < 0.003: #0.3%
                #     self.log('ignore small change !, %.2f' % self.dataclose[0])
                # elif self.datalow[0] < ((self.order_high_price -self.buyprice)*0.618 + self.buyprice):
                #     # SELL, SELL, SELL!!! (with all possible default parameters)
                #     self.log('SELL CREATE, %.2f' % self.dataclose[0])
                #     # Keep track of the created order to
                #     #  avoid a 2nd order
                #     self.order = self.close()
            elif self.user_position ==btc_enum.Position.Short: #Short(做空)
                # if self.smasig[0] > 0.0:
                #     self.close()
                if self.dataclose[0] < self.order_low_price:
                    self.order_low_price = self.datalow[0]
                if self.dataclose[0] > self.sellprice:
                    # self.close()
                    # print(self.dataclose[0])
                    if (self.dataclose[0] - self.sellprice) > 0.01: #0.3%  we are losing!!!!
                        self.close()
                elif abs(self.sellprice - self.dataclose[0])/self.sellprice < 0.005: #0.3%
                    self.log('ignore small change !, %.2f' % self.dataclose[0])
                elif self.dataclose[0] < self.sellprice:#we need more
                    if(self.dataclose[0] - self.order_low_price)/(self.sellprice-self.order_low_price) > 0.6 :
                        self.close()
                    # elif (self.sellprice-self.dataclose[0])/self.sellprice > 0.01:
                    #     self.close()
                    #     self.log('a good trade')

    def stop(self):
        self.log("trade num :%d , short shot times %d, short wrong times %d, long shot times %d,long wrong times %d"\
                 %(self.result.times,self.short_make_times,self.short_wrong_times,self.long_make_times,self.long_wrong_times))
        self.log('(MA Period %2d) Ending Value %.2f data offset:%d' %
                 (self.params.maperiod, self.broker.getvalue(), self.data_offset), doprint=True)

    def quit(self):
        self.env.runstop()

    def average_range(self,size):
        change = 0
        for i in range(0,size):
            change = change + (self.datahigh[-i]-self.datalow[-i])
        return (change/size)

    def average_volume(self,size):
        volume = 0
        for i in range(0,size):
            volume = volume + self.volume[-i]
        return (volume/size)

    def order_size(self):
        return ((self.broker.getvalue()*0.5+  _cash*0.1)/self.dataclose)

    def slop(self):
        pass

    def data_analyze(self):
        pass

    def linear_fitting(self,data,length):
        X = np.array(range(0,length)).reshape(length, 1)
        data_array= [data[-i] for i in range(length-1,-1,-1)]
        Y = np.array(data_array).reshape(length, 1)
        # 建立线性回归模型
        regr = linear_model.LinearRegression()
        # 拟合
        regr.fit(X, Y)
        # 不难得到直线的斜率、截距
        a, b = regr.coef_, regr.intercept_
        return a,b

    # def ma_

    # def judge_up(self,sma):
    #     if len(sma) < 3:
    #         return False
    #     if sma[0] > sma[-1] and sma[-1] > sma[-2] 

    # def  support_resistance():  


if __name__ == '__main__':
    currentDateAndTime = time.localtime()
    print(currentDateAndTime)
    # Create a cerebro entity
    cerebro = bt.Cerebro(stdstats=True)
    cerebro.addobserver(bt.observers.Broker)
    cerebro.addobserver(bt.observers.Trades)
    cerebro.addobserver(bt.observers.BuySell)
    # Add a strategy
    strats = cerebro.addstrategy(
        TestStrategy,
        maperiod=10,
        printlog=True,
        user_scope = btc_enum.Scope.SELL)

    # Datas are in a subfolder of the samples. Need to find where the script is
    # because it could have been called from anywhere
    modpath = os.path.dirname(os.path.abspath(sys.argv[0]))

    datapath = os.path.join(modpath, '..','datas','klines15m.csv')
    # Create a Data Feed
    data = BINACSVData(
        dataname=datapath,
        # Do not pass values before this date
        fromdate=datetime.datetime(2010, 1, 1),
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
    cerebro.broker.setcash(_cash)

    # Add a FixedSize sizer according to the stake
    cerebro.addsizer(bt.sizers.FixedSize, stake=1)

    # Set the commission
    cerebro.broker.setcommission(commission=0)

    # Run over everything
    cerebro.run(maxcpus=4)

    cerebro.plot()