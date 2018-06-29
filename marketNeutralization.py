import pandas as pd
import numpy as np
from datetime import datetime,timedelta
# from .optimizer_toolkit import *

import rqdatac
rqdatac.init('rice','rice',('192.168.10.64',16008))
from functools import reduce




def subnew_stocks_filter(stocks,date,subnewThres=5):
    """
    # 获得某日上市小于N天的次新股
    :param stocks: list 股票列表
    :param date: str eg. "2018-01-01"
    :param N: int 次新股过滤的阈值
    :return: list 列表中的次新股
    """
    # return [(rqdatac.instruments(s).listed_date) for s in stocks]
    return [s for s in stocks if (pd.Timestamp(date) - pd.Timestamp(rqdatac.instruments(s).listed_date)).days>subnewThres]

def st_stocks_filter(stocks,date):
    """
    获得某日的ST类股票
    :param stocks: list 股票列表
    :param date: 交易日
    :return: list 列表中st的股票
    """
    st_series = rqdatac.is_st_stock(stocks,start_date=date,end_date=date).iloc[-1]
    return st_series[~st_series].index.tolist()

def suspended_stocks_filter(stocks,date):
    """
    :param stocks:股票列表
    :param date: 检验停牌日期
    :return: list
    """
    # volume = rqdatac.get_price(stocks,start_date=date,end_date=date,fields="volume").iloc[0]
    # return volume[volume>0].index.tolist()
    return [s for s in stocks if not rqdatac.is_suspended(s,start_date=date,end_date=date).values[0,0]]

def low_liquidity_filter(stocks,date,percentileThres):
    """
    :param stocks: 股票列表
    :param date: 日期
    :param thres: 剔除换手率位于某百分位以下的股票，例如thres=5，则剔除换手率处于5分位以下的股票
    :return:list
    """
    liquidity = rqdatac.get_style_factor_exposure(stocks,date,date,factors="liquidity")['liquidity']

    return liquidity[liquidity>np.nanpercentile(liquidity,q=percentileThres)].index.get_level_values(0).unique().tolist()

def small_size_filter(stocks,date,percentileThres):
    """
    :param stocks: 股票列表
    :param date: 日期
    :param thres: 剔除市值位于某百分位以下的股票，例如thres=5，则剔除市值处于5分位以下的股票
    :return: list
    """
    marketCap = rqdatac.get_factor(stocks,"a_share_market_val",date=date)

    return marketCap[marketCap>np.nanpercentile(marketCap,q=percentileThres)].index.tolist()

def noisy_stocks_filter(stocks,date,subnewThres=350,percentileThres=5):
    """
    剔除ST股票、剔除次新股、剔除当日停牌、流动性(市值)某百分位以下的股票
    :param stocks: 股票列表
    :param date: 日期
    :param N: 剔除上市小于N天的次新股
    :param thres: 进行流动性和规模过滤的百分数阈值
    :return: list
    """
    filtered_stocks = st_stocks_filter(stocks,date)
    filtered_stocks = subnew_stocks_filter(filtered_stocks,date,subnewThres)
    filtered_stocks = suspended_stocks_filter(filtered_stocks, date)
    filtered_stocks = low_liquidity_filter(filtered_stocks,date,percentileThres)
    filtered_stocks = small_size_filter(filtered_stocks,date,percentileThres)
    return filtered_stocks


def get_explict_factor_returns(date):
    """
    :param date:日期
    :return:
    """

    previous_trading_date = rqdatac.get_previous_trading_date(date)

    all_a_stocks = rqdatac.all_instruments(type="CS",date=previous_trading_date).order_book_id.tolist()
    all_a_stocks = noisy_stocks_filter(all_a_stocks,previous_trading_date)
    factor_exposures = rqdatac.get_style_factor_exposure(all_a_stocks, previous_trading_date, previous_trading_date, "all").sort_index()
    factor_exposures.index=factor_exposures.index.droplevel(1)
    beta_size = factor_exposures[['size','beta']]

    quantileGroup = beta_size.apply(lambda x:pd.cut(x,bins=3,labels=False)+1).reset_index()
    quantileStocks = quantileGroup.groupby(['size','beta']).apply(lambda x:x.index.tolist())
    market_neutralize_stocks = quantileStocks.apply(
        lambda x: pd.Series(all_a_stocks).loc[x].values.tolist()).values.tolist()

    closePrice = rqdatac.get_price(all_a_stocks, rqdatac.get_previous_trading_date(previous_trading_date),
                                   previous_trading_date, fields="close")
    priceChange = closePrice.pct_change().iloc[-1]

    def _calc_single_explict_returns(factor):

        _factor_exposure = factor_exposures[factor]
        def _deuce(series):
            median = series.median()
            return [series[series<=median].index.tolist(),series[series>median].index.tolist()]

        deuceResults = np.array([_deuce(_factor_exposure[neutralized_stks]) for neutralized_stks in market_neutralize_stocks]).flatten()

        short_stocksList = list(reduce(lambda x,y:set(x)|set(y),np.array([s for i,s in enumerate(deuceResults) if i%2==0])))
        long_stockList = list(reduce(lambda x,y:set(x)|set(y),np.array([s for i,s in enumerate(deuceResults) if i%2==1])))

        return priceChange[long_stockList].mean() - priceChange[short_stocksList].mean()

    return factor_exposures.apply(lambda x:_calc_single_explict_returns(x.name))


def calc_index_explict_factor_returns(indexCode,date):

    previous_trading_date = rqdatac.get_previous_trading_date(date)

    indexComponents = rqdatac.index_components(indexCode,date=date)

    factor_exposures = rqdatac.get_style_factor_exposure(indexComponents, previous_trading_date, previous_trading_date, "all").sort_index()
    factor_exposures.index=factor_exposures.index.droplevel(1)
    sizeBeta = factor_exposures[['size','beta']]

    quantileGroup = sizeBeta.apply(lambda x:pd.cut(x,bins=3,labels=False)+1).reset_index()
    quantileStocks = quantileGroup.groupby(['size','beta']).apply(lambda x:x.index.tolist())
    market_neutralize_stocks = quantileStocks.apply(
        lambda x: pd.Series(indexComponents).loc[x].values.tolist()).values.tolist()

    def _calc_single_explict_returns(factor):

        _factor_exposure = factor_exposures[factor]
        def _deuce(series):
            median = series.median()
            return [series[series<=median].index.tolist(),series[series>median].index.tolist()]

        deuceResults = np.array([_deuce(_factor_exposure[neutralized_stks]) for neutralized_stks in market_neutralize_stocks]).flatten()

        short_stocksList = list(reduce(lambda x,y:set(x)|set(y),np.array([s for i,s in enumerate(deuceResults) if i%2==0])))
        long_stockList = list(reduce(lambda x,y:set(x)|set(y),np.array([s for i,s in enumerate(deuceResults) if i%2==1])))

        closePrice = rqdatac.get_price_change_rate(indexComponents,date,date).iloc[0]
        return closePrice[long_stockList].mean() - closePrice[short_stocksList].mean()

    return factor_exposures.apply(lambda x:_calc_single_explict_returns(x.name))

