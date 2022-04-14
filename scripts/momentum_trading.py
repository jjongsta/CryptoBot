import pandas as pd
import numpy as np
import time
from datetime import datetime, timedelta
import cbpro

def make_buy_orders(coin, funds, size, atr):
    print(auth_client.place_market_order(product_id=f'{coin}-USD', side='buy', funds=funds))
    # stop loss at 2 * ATR
    stop_price = buy_price - 2 * atr
    auth_client.place_order(product_id=f'{coin}-USD', 
                    order_type='limit',
                    side='sell',
                    stop='loss',
                    stop_price=stop_price,
                    price=stop_price,
                    size=size)

# calculate ATR and rolling high and low price
def _get_atr(df, window_atr=20, window_high=20, window_low=10):
    df['pclose'] = df['close'].shift(1)
    df['diff1'] = abs(df['high'] - df['low'])
    df['diff2'] = abs(df['pclose'] - df['high'])
    df['diff3'] = abs(df['pclose'] - df['low'])
    df['tr'] = df[['diff1', 'diff2', 'diff3']].max(axis=1)
    df['atr'] = df['tr'].rolling(window=window_atr).mean()
    df['rolling_high'] = df.high.rolling(window=window_high).max()
    df['rolling_low'] = df.low.rolling(window=window_low).min()
    
    return df

def lambda_handler(event, context):
    # TODO implement
    API_KEY = ''
    API_SECRET = ''
    API_PASS = ''
    
    auth_client = cbpro.AuthenticatedClient(API_KEY, API_SECRET, API_PASS)
    pub_client = cbpro.PublicClient()
    
    # parameters
    coin = 'ETH'
    window_atr = 5
    window_high = 5
    window_low = 10
    n = 0.03 # pct of total port val to trade
    max_pyrm_num = 4
    
    print('==========================================')
    print("start trading...")
    
    # get current time
    cur_time = pub_client.get_product_ticker(f'{coin}-USD')['time']
    cur_time_parsed = datetime.strptime(cur_time, '%Y-%m-%dT%H:%M:%S.%fZ')
    
    print(f'cur_time: {cur_time_parsed}')
    
    # get account_info for holding coins
    acc_info = {}

    for data in auth_client.get_accounts():
        currency = data['currency']
        if currency in ['USD',f'{coin}']:
            acc_info[currency] = data

    # get price data
    df = pd.DataFrame(pub_client.get_product_historic_rates(f'{coin}-USD', granularity=24*60*60),
                  columns=['time','low','high','open','close','volume']).sort_values('time')
    df['time'] = pd.to_datetime(df['time'],unit='s')
    df.set_index('time', inplace=True)

    df = _get_atr(df, window_atr=window_atr, window_high=window_high, window_low=window_low)
    atr = df['atr']

    df = df.iloc[-2,:]
    
    print(df)
    
    # current account status
    cur_price = float(pub_client.get_product_24hr_stats(f'{coin}-USD')['last'])
    cur_hold = float(acc_info[coin]['balance'])
    cur_cash = float(acc_info['USD']['balance'])
    cur_port_val = cur_hold * cur_price + cur_cash

    print('----------------------------------')
    print(f'cur_price: {cur_price}')
    print(f'cur_hold: {cur_hold}')
    print(f'cur_cash: {cur_cash}')
    print(f'cur_port_val: {cur_port_val}')
    
    # get last buy price and get # of pyramiding
    num_pyrm = -1
    last_trade_day = -1
    last_buy_price = -1
    
    for i, order in enumerate(auth_client.get_fills(product_id=f'{coin}-USD')):
        if i == 0:
            last_buy_price = float(order['price'])
            last_trade_day = datetime.strptime(order['created_at'], '%Y-%m-%dT%H:%M:%S.%fZ').day
        if order['side'] == 'sell':
            print(f'last_buy_price: {last_buy_price}')
            print(f'last_trade_day: {last_trade_day}')
            print(f'number of pyramiding: {num_pyrm}')
            break
        num_pyrm += 1
        
    # if the most trade was made in the previous day, go through order process
    if last_trade_day < cur_time_parsed.day:

        # if current price is higher than rolling high
        if cur_price > df['rolling_high']:
            
            print('Buy signal!')
            
            # if we have no position
            if cur_hold * cur_price < 1.:
                num_coins = cur_port_val * n / atr
                funds = num_coins * cur_price
                size = num_coins
                make_buy_orders(coin, funds, size, atr)

            # if we have position, and price has increased by 1 ATR, do pyramiding
            elif (cur_price > last_buy_price + atr) & (num_pyrm < max_pyrm_num):
                print(auth_client.cancel_all(product_id=f'{coin}-USD')) # cancel previous stop order
                num_coins = cur_port_val * n / atr
                funds = min(cur_price * num_coins, cur_cash) # if we don't have enough cash, we all-in
                num_coins = funds/cur_price
                size = num_coins + cur_hold
                make_buy_orders(coin, funds, size, atr)
                
                print('Pyramiding...')

        # if current price is lower than rolling low and we have position, sell all holdings
        elif (cur_price < df['rolling_low']) & (cur_hold * cur_price > 1.):
            print(auth_client.place_market_order(product_id=f'{coin}-USD', side='sell', size=cur_hold))
            
            print('Sell all position')
            
        else:
            print('No buy or sell signal!')
            pass
        
    else:
        print('Order has been placed on this day...')
        pass

                    
