import json
import pandas as pd
import numpy as np
import time
from datetime import datetime, timedelta
import cbpro

def lambda_handler(event, context):
    # TODO implement
    API_KEY = ''
    API_SECRET = ''
    API_PASS = ''
    
    auth_client = cbpro.AuthenticatedClient(API_KEY, API_SECRET, API_PASS)
    pub_client = cbpro.PublicClient()
    
    print('---------------------')
    print("start trading...")
    
    # get account_info for holding coins
    acc_info = {}

    for data in auth_client.get_accounts():
        currency = data['currency']
        acc_info[currency] = data
    
    time = pub_client.get_product_ticker('BTC-USD')['time']
    parsed_time = datetime.strptime(time, '%Y-%m-%dT%H:%M:%S.%fZ')
    print(f'Current time: {time}')

    num_ticker = 4
    k = 0.6

    df_dict = {}

    # if the time is 1 day candle, clear all positions
    if (parsed_time.minute == 0) & (parsed_time.hour == 0):
        for coin in acc_info.keys():
            coin_size = float(acc_info[coin]['available'])
            if coin_size > 0 and 'USD' not in coin:
                price = float(pub_client.get_product_24hr_stats(f'{coin}-USD')['last'])
                usd_size = round(price * coin_size, 2)
                print(f'Selling {coin}, size: ${usd_size}')
                print(auth_client.place_market_order(product_id=f'{coin}-USD', side='sell', funds=usd_size))
                time.sleep(0.1)

    # if it's not 1 day candle, monitor prices
    else:

        # get candle info 
        for coin in acc_info.keys():
            df = pd.DataFrame(pub_client.get_product_historic_rates(f'{coin}-USD', granularity=24*60*60),
                          columns=['time','low','high','open','close','volume']).sort_values('time')
            df['time'] = pd.to_datetime(df['time'],unit='s')
            df.set_index('time', inplace=True)
            df_dict[coin] = df.iloc[-2:,:] # we need today & yesterday's data

        # get volume in usd
        df_vol = pd.DataFrame(columns=['coin','vol_usd'])
        for coin in df_dict.keys():
            try:
                past_data = df_dict[coin].iloc[0,:]
                vol_usd = past_data['volume'] * past_data['close']
                df_vol = df_vol.append({'coin':coin, 'vol_usd':vol_usd}, ignore_index=True)
            except:
                pass

        # list top X coins by volume
        final_list = df_vol.sort_values('vol_usd', ascending=False).head(num_ticker).coin.tolist()
        print(f'Final list: {final_list}')

        # function for getting buy signal
        def get_signal(past_high, past_low, cur_open, cur_high, k):
            price_range = past_high - past_low
            buy_price = cur_open + price_range * k
            print(f'Buy price: ${buy_price}')
            # if current day's price has satisfied the standard, we buy
            if cur_high > buy_price:
                return buy_price
            else:
                # no buy signal
                return -1

        # get list of coins we hold
        coins_holding_list = []
        for data in acc_info.values():
            coin = data['currency']
            coin_amount = float(data['available'])
            if coin_amount > 0 and 'USD' not in coin:
                price = float(pub_client.get_product_24hr_stats(f'{coin}-USD')['last'])
                # when value of the holding coin in USD is greater than $0.1, we add that coin as our holding list
                if coin_amount * price > 0.1:
                    coins_holding_list.append(coin)
        num_coins_holding = len(coins_holding_list)
        print(coins_holding_list)

        # market buy coins
        for coin in final_list:

            # if we don't already have a position in this coin, we buy
            if coin not in coins_holding_list:
                print(f'Coin: {coin}')
                past_data = df_dict[coin].iloc[0,:]
                cur_data = df_dict[coin].iloc[1,:]
                cur_price = float(pub_client.get_product_24hr_stats(f'{coin}-USD')['last'])
                buy_price = get_signal(past_data['high'], past_data['low'], cur_data['open'], cur_price, k)

                # if we have buy signal
                if buy_price > 0:
                    print(f'Buy price: ${buy_price}')
                    size = round(float(acc_info['USD']['available'])/(num_ticker - num_coins_holding), 2)
                    auth_client.place_market_order(product_id=f'{coin}-USD', side='buy', funds=size)
                    
                    print(f'Purchased: {coin}')
                    print(f'Size: ${size}')
                else:
                    print('Signal not found...')
                    
