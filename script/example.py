from __future__ import (absolute_import, division, print_function,
                        unicode_literals)

import datetime  # For datetime objects
import os.path  # To manage paths
import sys,time  # To find out the script name (in argv[0])


# Import the backtrader platform
import backtrader as bt

from load_binance_csv import BINACSVData
import btc_enum

class TradeResult():
    def __init__(self) -> None:
        self.times = 0

_cash = 10000

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
                if self.user_position == btc_enum.Position.Short:
                    if self.sellprice < self.buyprice:
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
                    if self.sellprice > self.buyprice:
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
                if self.sma_short[0] > self.sma_short[-1] and self.sma_short[-1] > self.sma_short[-2] and  self.sma_short[-2] > self.sma_short[-3] \
                    and self.sma_middle[0] > self.sma_middle[-1] \
                    and self.dataclose[0] > self.sma_short[0]:

                    # BUY, BUY, BUY!!! (with all possible default parameters)
                    self.log('BUY CREATE, %.2f' % self.dataclose[0])

                    # Keep track of the created order to avoid a 2nd order
                    self.order = self.buy(size=self.order_size())
                    self.order_high_price = self.dataclose[0]
                    self.result.times = self.result.times + 1
                    self.user_position = btc_enum.Position.Long
            elif self.params.user_scope in [btc_enum.Scope.SELL,btc_enum.Scope.ALL]:
                if self.sma_short[0] < self.sma_short[-1] \
                    and self.sma_middle[0] < self.sma_middle[-1] \
                    and (self.dataopen[0]-self.dataclose[0])> self.average_range()*2 \
                    and self.volume[0] > self.average_volume()*2 :

                    # BUY, BUY, BUY!!! (with all possible default parameters)
                    self.log('SELL CREATE, %.2f' % self.dataclose[0])

                    # Keep track of the created order to avoid a 2nd order
                    self.order = self.sell(size=self.order_size())
                    self.order_low_price = self.dataclose[0]
                    self.result.times = self.result.times + 1
                    self.user_position = btc_enum.Position.Short
        else:   #in market
            if self.user_position ==btc_enum.Position.Long:#Long(做多)
                if self.datahigh[0] > self.order_high_price:
                    self.order_high_price = self.datahigh[0]

                if (self.order_high_price -self.buyprice)/self.buyprice < 0.003: #0.3%
                    self.log('ignore small change !, %.2f' % self.dataclose[0])
                elif self.datalow[0] < ((self.order_high_price -self.buyprice)*0.618 + self.buyprice):
                    # SELL, SELL, SELL!!! (with all possible default parameters)
                    self.log('SELL CREATE, %.2f' % self.dataclose[0])

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
                if self.dataclose[0] < self.order_low_price:
                    self.order_low_price = self.dataclose[0]
                if self.dataclose[0] > self.sellprice:
                    self.close()
                    # print(self.dataclose[0])
                    # if (self.dataclose[0] - self.sellprice) > 0.003: #0.3%  we are losing!!!!
                    #     self.close()
                elif abs(self.sellprice - self.dataclose[0])/self.sellprice < 0.003: #0.3%
                    self.log('ignore small change !, %.2f' % self.dataclose[0])
                elif self.dataclose[0] < self.sellprice:#we need more
                    if(self.dataclose[0] - self.order_low_price)/(self.sellprice-self.order_low_price) > 0.5 \
                        or self.sma_middle[0] > self.sma_middle[-1]:
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

    def average_range(self):
        change = 0
        for i in range(0,99):
            change = change + (self.datahigh[-i]-self.datalow[-i])
        return (change/99)

    def average_volume(self):
        volume = 0
        for i in range(0,99):
            volume = volume + self.volume[-i]
        return (volume/25)

    def order_size(self):
        return ((self.broker.getvalue()*0.5+  _cash*0.1)/self.dataclose)

    # def ma_

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

    # cerebro.plot()