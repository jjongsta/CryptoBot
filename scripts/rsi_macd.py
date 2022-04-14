import cbpro
import pandas as pd
import numpy as np
import schedule
import time
from datetime import datetime, timedelta
import yaml

yaml_filename = 'jay_cbpro_config.yaml'
my_yaml_file = open(f"../../{yaml_filename}")

yaml_dict = yaml.load(my_yaml_file, Loader=yaml.FullLoader)

locals().update(yaml_dict["cbpro"])

auth_client = cbpro.AuthenticatedClient(API_KEY, API_SECRET, API_PASS)
pub_client = cbpro.PublicClient()


def main():
    print("start trading...")
    
    """

    BTC, ETH, ADA, ZEC

    """
    acc_info = {'BTC':None,
                'ETH':None,
                'ADA':None,
                'ZEC':None,
                'USDC':None}

    for coin in acc_info.keys():
        temp = {'id':None, 'amount':None}
        for acc in auth_client.get_accounts():
            if acc['currency'] == coin:
                temp['id'] = acc['id']
                temp['amount'] = auth_client.get_account(acc['id'])['available']
                acc_info[coin] = temp

    """

    We are trading in an hour cadence

    """

    price_info = {'BTC':None,
                  'ETH':None,
                  'ADA':None,
                  'ZEC':None}

    for coin in price_info.keys():
        temp = pd.DataFrame(pub_client.get_product_historic_rates(f'{coin}-USDC', granularity=3600),
                                        columns=['time','low','high','open','close','volume']).sort_values('time')
        temp['time'] = pd.to_datetime(temp['time'],unit='s')
        temp.set_index('time', inplace=True)
        price_info[coin] = temp

    # helper functions for technical indicators
    def _get_rsi(price, window=14):
        delta = price['close'].diff()
        up_days = delta.copy()
        up_days[delta<=0]=0.0
        down_days = abs(delta.copy())
        down_days[delta>0]=0.0
        RS_up = up_days.rolling(window).mean()
        RS_down = down_days.rolling(window).mean()
        rsi= 100-100/(1+RS_up/RS_down)
        return rsi


    def _get_macd(price, window_1=12, window_2=26, os_window=9):
        ewm_12 = price['close'].ewm(span=window_1, adjust=False).mean()
        ewm_26 = price['close'].ewm(span=window_2, adjust=False).mean()
        macd = ewm_12 - ewm_26
        macd_ema = macd.ewm(span=os_window, adjust=False).mean()
        os = (macd - macd_ema)
        return macd, macd_ema, os

    # dummy get_signal function
    def get_signal(time, ind):

        # get indicators
        rsi, macd, macd_ema, os, vol = ind

        # get index
        time_60min = time
        time_60min_1 = time_60min - timedelta(minutes=60)
        time_60min = time_60min.strftime('%Y-%m-%d %H:00:00')
        time_60min_1 = time_60min_1.strftime('%Y-%m-%d %H:00:00')

        # dummy strategy
        if rsi.loc[time_60min] < 40 and (os.loc[time_60min_1] < 0 and os.loc[time_60min] > 0):
            return 1.0
        elif rsi.loc[time_60min] > 70 and (os.loc[time_60min_1] > 0 and os.loc[time_60min] < 0):
            return -1.0
        else:
            return 0

    signal_info = {'BTC':None,
                  'ETH':None,
                  'ADA':None,
                  'ZEC':None}

    for coin in signal_info.keys():
        # get indicators
        price = price_info[coin]
        rsi = _get_rsi(price)
        macd, macd_ema, os = _get_macd(price)
        vol = price['volume']
        ind = rsi, macd, macd_ema, os, vol

        # get signal
        time = price_info[coin].index[-1]
        print('===========================')
        print(coin)
        print(time)
        print(rsi[-1])
        print(os[-1])
        signal = get_signal(time, ind)

        signal_info[coin] = signal

    sl_pct = 0.05
    coins_unholding = len(acc_info.keys())

    for coin in acc_info.keys():
        if float(acc_info[coin]['amount']) > 0 and coin != 'USDC':
            coins_unholding -= 1

    print(f'Coins unholding: {coins_unholding}')

    for coin in signal_info.keys():

        usdc_amount = round(float(acc_info['USDC']['amount'])/coins_unholding, 0)
        coin_amount = float(acc_info[coin]['amount'])
        signal = signal_info[coin]

        print('=============')
        print(f'Coin: {coin}')
        print(f'USDC: {usdc_amount}')

        # buy
        if signal > 0 and usdc_amount > 0.:
            print('buy')
            size = str(round(usdc_amount*signal,2))
            auth_client.place_market_order(product_id=f'{coin}-USDC',
                                           side='buy',
                                           funds=size)
            # stop order
            recent_price = next(pub_client.get_product_trades(product_id=f'{coin}-USDC'))['price']
            stoploss_price_trigger = str(round(float(recent_price)*(1-sl_pct),2))
            stoploss_price = str(round(float(recent_price)*(1-sl_pct-0.01),2))
            auth_client.place_order(product_id=f'{coin}-USDC', 
                                    order_type='limit',
                                    side='sell',
                                    stop='loss',
                                    stop_price=stoploss_price_trigger,
                                    price=stoploss_price,
                                    size=size)
            print(f'stoploss price: {stoploss_price}')

        # sell
        elif signal < 0 and coin_amount > 0.:
            print('sell')
            size = str(round(coin_amount*signal,2))
            auth_client.place_market_order(product_id=f'{coin}-USDC',
                                           side='sell',
                                           funds=size)
            # cancel stoploss order
            auth_client.cancel_all(product_id=f'{coin}-USDC')
        else:
            print('hold')
            pass
    
        
if __name__ == "__main__":
    schedule.every().hour.at(":01").do(main)
#     schedule.every().minute.at(":17").do(job)
    while True:
        print('schedule job running...')
        schedule.run_pending()
        time.sleep(60)