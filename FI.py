import numpy as np
#Made to be run on Quantconnect.com
class Fundamental_Indexation(QCAlgorithm):


    def Initialize(self):
        self.SetStartDate(2000, 1, 1)    # Set Start Date
        self.SetCash(100000)             # Set Strategy Cash

        self.UniverseSettings.Resolution = Resolution.Daily
        self.AddUniverse(self.CoarseSelectionFunction, self.FineSelectionFunction)

        self.num_coarse = 3000            # Number of symbols selected at Coarse Selection
        self.num_long = 120                # Number of stocks to long
        
        self.longSymbols = []            # Contains the stocks we'd like to long


        self.nextLiquidate = self.Time   # Initialize last trade time
        self.rebalance_days = 360

        # Set the weights of each factor
        self.beta_t = 1
        self.beta_r = 1
        self.beta_o = 1
        self.beta_d = 1
        
        # Set the risk management of each factor
        
        self.maximumDrawdownPercent = -0.15 # Invest in bonds' ETF if reached
        self.initialised = False
        self.portfolioHigh = 0
        self.AddEquity("TLT", Resolution.Daily) # 20+ Year treasury bond ETF
        self.AddEquity("SHY", Resolution.Daily) # 1-3 Year treasury bond ETF



    def CoarseSelectionFunction(self, coarse):
        '''Drop securities which have no fundamental data or have too low prices.
        Select those with highest by dollar volume'''

        if self.Time < self.nextLiquidate:
            return Universe.Unchanged

        selected = sorted([x for x in coarse if x.HasFundamentalData and x.Price > 5],
                          key=lambda x: x.DollarVolume, reverse=True)

        return [x.Symbol for x in selected[:self.num_coarse]]


    def FineSelectionFunction(self, fine):
       

        # Select stocks with these 4 factors:
        # TV -- Tangible Book Value
        # TR -- Total Revenue
        # OI -- Operation Income
        # DP -- Total Dividend Paid 
        
        filtered = [x for x in fine if x.FinancialStatements.BalanceSheet.TangibleBookValue
                                    and x.FinancialStatements.IncomeStatement.TotalRevenue
                                    and x.FinancialStatements.IncomeStatement.OperatingIncome
                                    and (x.CompanyReference.PrimaryExchangeID == "NAS" or x.CompanyReference.PrimaryExchangeID == "NYS") # US stocks
                                    and x.FinancialStatements.CashFlowStatement.DividendsPaidDirect
                                    ]
        # Sort by factors
        sortedByTV = sorted(filtered, key=lambda x: x.FinancialStatements.BalanceSheet.TangibleBookValue.TwelveMonths, reverse=True)
        sortedByTR = sorted(filtered, key=lambda x: x.FinancialStatements.IncomeStatement.TotalRevenue.TwelveMonths, reverse=True)
        sortedByOI = sorted(filtered, key=lambda x: x.FinancialStatements.IncomeStatement.OperatingIncome.TwelveMonths, reverse=True)
        sortedByDP = sorted(filtered, key=lambda x: x.FinancialStatements.CashFlowStatement.DividendsPaidDirect.TwelveMonths, reverse=True)
        #employement is not available on QC

        stockBySymbol = {}

        # Get the rank based on 5 factors for every stock
        for index, stock in enumerate(sortedByTV):
            TVRank = np.mean(self.beta_t * index)
            TRRank = np.mean(self.beta_r * sortedByTR.index(stock))
            OIRank = np.mean(self.beta_o * sortedByOI.index(stock))
            DPRank = np.mean(self.beta_d * sortedByDP.index(stock))
            avgRank = TVRank + TRRank + OIRank + DPRank
            stockBySymbol[stock.Symbol] = avgRank

        sorted_dict = sorted(stockBySymbol.items(), key = lambda x: x[1], reverse = True)
        symbols = [x[0] for x in sorted_dict]

        # Pick the stocks with the highest scores to long
        self.longSymbols= symbols[:self.num_long]

        return self.longSymbols 


    def OnData(self, data):
        '''Rebalance Every self.rebalance_days'''


        # Liquidate stocks in the end of every month
        if self.Time >= self.nextLiquidate:
            for holding in self.Portfolio.Values:
                # If the holding is in the long/short list for the next month, don't liquidate
                if holding.Symbol in self.longSymbols :
                    continue
                # If the holding is not in the list, liquidate
                if holding.Invested:
                    self.Liquidate(holding.Symbol)

        count = len(self.longSymbols)
        
        currentValue = self.Portfolio.TotalPortfolioValue
        
        if not self.initialised:
            self.portfolioHigh = currentValue   # Set initial portfolio value
            self.initialised = True
            
        if self.portfolioHigh < currentValue:
            self.portfolioHigh = currentValue
            
        pnl = (float(currentValue) / float(self.portfolioHigh)) - 1.0
        
        
        if pnl < self.maximumDrawdownPercent :
           
            self.Liquidate()
            
            self.portfolioHigh = 0
            
            self.SetHoldings('TLT', 0.50)
            
            self.SetHoldings('SHY', 0.50)
            
            return
           

        # It means the long lists for the month have been cleared
        if count == 0: 
            return

        # Open long position at the start of every month
        for symbol in self.longSymbols:
            self.SetHoldings(symbol, 1/count)

        # Set the Liquidate Date
        self.nextLiquidate = self.Time + timedelta(self.rebalance_days)

        # After opening positions, clear the long symbol list until next universe selection
        self.longSymbols.clear()
