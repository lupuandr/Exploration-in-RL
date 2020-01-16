# !/usr/bin/env python


import numpy as np
import random
import copy
from scipy.stats import bernoulli
from tqdm import tqdm

from environments import make_riverSwim, deep_sea, TabularMDP

class RLSVI(object):
    def __init__(self,env,K):
        self.env = env
        self.K = K
        self.buffer = {key: [] for key in env.R.keys()}
        self.buf = []
        self.Q = {key: 0.0 for key in self.buffer.keys()}
        self.prior_variance = 1.0
        self.noise_mean = -0.1
        self.noise_variance = 0.05
        self.action_set = (0, 1)

    def _random_argmax(self, action_values):
        argmax_list = np.where(action_values==np.max(action_values))[0]
        return self.action_set[argmax_list[np.random.randint(argmax_list.size)]]

    def name(self):
        return 'RLSVI'

    def act(self,s):
        x = [self.Q[(s,a)] for a in range(self.env.nAction)]
        return self.env.argmax(np.array(x))

    def update_buffer(self,data):
        s,a,r,s_ = data[0],data[1],data[2],data[3]
        self.buffer[(s,a)].append((r,s_))

    def learn_from_buffer(self):
        perturbed_buffer = {key: [(transition[0] + np.sqrt(self.noise_variance) * np.random.randn() + self.noise_mean,
                                   transition[1]) for transition in self.buffer[key]]
                            for key in self.buffer.keys()}
        random_Q = {key: np.sqrt(self.prior_variance) * np.random.randn() for key in self.buffer.keys()}
        Q = {key: 0.0 for key in self.buffer.keys()}
        Q_temp = {key: 0.0 for key in self.buffer.keys()}
        for n in range(self.env.epLen):
            for key in self.buffer.keys():
                q = 0.0
                for transition in perturbed_buffer[key]:
                    if transition[1] == None:
                        q += transition[0]
                    else:
                        #print(Q)
                        v = max(Q[(transition[1], a)] for a in self.action_set)
                        q += transition[0] + v
                Q_temp[key] = (1.0 / ((len(self.buffer[key]) / self.noise_variance) + (1.0 / self.prior_variance))) \
                              * ((q / self.noise_variance) + (random_Q[key] / self.prior_variance))
            Q = Q_temp
            Q_temp = {key: 0.0 for key in self.buffer.keys()}
        self.Q = Q

    def run(self):
        R = []
        reward = 0.0
        for l in tqdm(range(0,self.K)):
            #if (l + 1 % 150) == 0:
            #    agent.buffer_reset()
            self.env.reset()
            done = 0
            while done != 1:
                s = self.env.state
                #print(s)
                a = self.act(s)
                r,s_,done = self.env.advance(a)
                reward += r
                #print(r)
                if done == 1:
                    self.update_buffer((s,a,r,None))
                else:
                    self.update_buffer((s,a,r,s_))

            self.learn_from_buffer()
            R.append(reward)
        return R

class PSRL(object):
    def __init__(self,env):
        self.env = env
        self.alpha = {key: np.zeros(env.nState) for key in env.R.keys()} # need a more efficent method of creating this
        self.mu = {key: 0.0 for key in env.R.keys()}
        self.sigma2 = {key: 1.0 for key in env.R.keys()} #also this can be higher, no idea how initialization of this matrix effects learning, I assume higher initial values "slows" learning
        self.sigma_r = 0.00001 #since our reward is deterministic, this keeps from the estimate of the reward from centering around the mean reward can this value be learned?
        self.buffer = {h: [] for h in range(env.epLen)}
        self.P = {key: np.zeros(env.nState) for key in env.R.keys()}
        self.R = {key: 0.0 for key in env.R.keys()}
        self.Rbar = {key: 0.0 for key in env.R.keys()}
        self.Q = {key: 0.0 for key in env.R.keys()}

    def act(self,s):
        x = np.array([self.Q[(s,a)] for a in range(self.env.nAction)])
        return env.argmax(x)

    def learn(self,l):
        self.update_statistics(l)
        self.update_priors()
        self.update_value_functions()

    def update_buffer(self,s,a,r,s_,t):
        self.buffer[t].append((s,a,r,s_))

    def update_statistics(self,l):
        for d in self.buffer.values():
            #print(d)
            s,a,r,s_ = d[l][0],d[l][1],d[l][2],d[l][3]
            if s_ != None:
                self.alpha[(s,a)][s_] = self.alpha[(s,a)][s_] + 1
            self.mu[(s,a)] = (1/self.sigma2[(s,a)]*self.mu[(s,a)] + 1/self.sigma_r*r)/(1/self.sigma2[(s,a)] + 1/self.sigma_r)
            self.sigma2[(s,a)] = 1 / (1/self.sigma2[(s,a)] + 1/self.sigma_r)

    def update_priors(self):
        for s in range(env.nState):
            for a in range(env.nAction):
                self.Rbar[(s,a)] = np.random.normal(self.mu[(s,a)],self.sigma2[(s,a)])
                self.R[(s,a)] = np.random.normal(self.Rbar[s,a],self.sigma_r)
                self.P[(s,a)] = np.random.dirichlet(self.alpha[(s,a)] + 0.003) #since numpy's dirichlet doesn't take zeros add a small numerical value for stability

    def update_value_functions(self):
        Q = {key: 0.0 for key in env.R.keys()}
        V = np.zeros(env.nState) #need to make this a dictionary
        for _ in range(env.epLen+10): #why not? Seems to improve 'stability' to convergence of 'optimal' Q-values
            for s in range(env.nState):
                for a in range(env.nAction):
                    w = np.random.normal(0,(pow(env.epLen+1,2))/(max(sum(self.alpha[s,a])-2,1)))
                    Q[(s,a)] = self.R[(s,a)] + np.inner(self.P[(s,a)],V) + w
                V[s] = max([Q[(s,a_)] for a_ in range(env.nAction)])
        self.Q = Q.copy()
        self.V = V

class UCRL_VTR(object):
    '''
    Algorithm 1 as described in the paper Model-Based RL with
    Value-Target Regression
    The algorithm assumes that the rewards are in the [0,1] interval.
    '''
    def __init__(self,env,K,random_explore):
        self.env = env
        self.K = K
        # A unit test that randomly explores for a period of time then learns from that experience
        # Here self.random_explore is a way to select a period of random exploration.
        # When the current episode k > total number of episodes K divided by self.random_explore
        # the algorithm switches to the greedy action with respect to its action value Q(s,a).
        if random_explore:
            self.random_explore = 10
        else:
            self.random_explore = self.K
        # Here the dimension (self.d) for the Tabular setting is |S x A x S| as stated in Appendix B
        self.d = self.env.nState * self.env.nAction * self.env.nState
        # In the tabular setting the basis models is just the dxd identity matrix, see Appendix B
        self.P_basis = np.identity(self.d)
        #Our Q-values are initialized as a 2d numpy array, will eventually convert to a dictionary
        self.Q = [np.zeros((self.env.nState,self.env.nAction)) for i in range(self.env.epLen)]
        #Our State Value function is initialized as a 1d numpy error, will eventually convert to a dictionary
        self.V = [np.zeros(self.env.nState) for i in range(self.env.epLen+1)] # self.V[env.epLen] stays zero
        self.create_value_functions()
        #The index of each (s,a,s') tuple, see Appendix B
        self.sigma = {}
        self.state_idx = {}
        self.createIdx()
        #See Step 2, of algorithm 1
#         self.M = env.epLen**2*self.d*np.identity(self.d)
        # For use in the confidence bound bonus term, see Beta function down below
        self.lam = 1.0
        #Self.L is no longer need, but will keep for now.
        self.L = 1.0
        self.M = np.identity(self.d)*self.lam
        self.Minv = np.identity(self.d)*(1/self.lam)
        #See Step 2
        self.w = np.zeros(self.d)
        #See Step 2
        self.theta = np.dot(self.Minv,self.w)
        #See Step 3
        self.delta = 1/self.K
        #m_2 >= the 2-norm of theta_star, see Bandit Algorithms Theorem 20.5
        self.m_2 = 3.0
#         #Initialize the predicted value of the basis models, see equation 3
#         self.X = np.zeros((env.epLen,self.d))

    def create_value_functions(self):
        Q = {}
        q = {}
        V = {}
        v = {}
        for h in range(self.env.epLen):
            for s in self.env.states.keys():
                v[(s)] = 0
                for a in range(self.env.nAction):
                    q[(s,a)] = 0
            Q[h] = q
            V[h] = v
        V[h+1] = v
        #self.V = V.copy()
        #self.Q = Q.copy()


    def feature_vector(self,s,a,h):
        '''
        Returning sum_{s'} V[h+1][s'] P_dot(s'|s,a),
        with V stored in self.
        Inputs:
            s - the state
            a - the action
            h - the current timestep within the episode
        '''
        sums = np.zeros(self.d)
        for s_ in self.env.states.keys():
            #print(s,s_)
            sums += self.V[h+1][self.state_idx[s_]] * self.P_basis[self.sigma[(s,a,s_)]]
        return sums

    def proj(self, x, lo, hi):
        '''Projects the value of x into the [lo,hi] interval'''
        return max(min(x,hi),lo)

    def update_Q(self,s,a,k,h):
        '''
        A function that updates both Q and V, Q is updated according to equation 4 and
        V is updated according to equation 2
        Inputs:
            s - the state
            a - the action
            k - the current episode
            h - the current timestep within the episode
        Currently, does not properly compute the Q-values but it does seem to learn theta_star
        '''
        #Here env.R[(s,a)][0] is the true reward from the environment
        # Alex's code: X = self.X[h,:]
        # Suggested code:
        X = self.feature_vector(s,a,h)
        self.Q[h][self.state_idx[s],a] = self.proj(self.env.R[(s,a)][0] + np.dot(X,self.theta) + self.Beta(k) \
            * np.sqrt(np.dot(np.dot(np.transpose(X),np.linalg.inv(self.M)),X)), 0, self.env.epLen )
        self.V[h][self.state_idx[s]] = max(self.Q[h][self.state_idx[s],:])

    def update_Qend(self,k):
        '''
        A function that updates both Q and V at the end of each episode, see step 16 of algorithm 1
        Inputs:
            k - the current episode
        '''
        #step 16
        for h in range(self.env.epLen-1,-1,-1):
            for s in self.env.states.keys():
                for a in range(self.env.nAction):
                    #Here env.R[(s,a)][0] is the true reward from the environment
                    # Alex's code: X = self.X[h,:]
                    # Suggested code:
                    self.update_Q(s,a,k,h)
                self.V[h][self.state_idx[s]] = max(self.Q[h][self.state_idx[s],:])

    def update_stat(self,s,a,s_,h):
        '''
        A function that performs steps 9-13 of algorithm 1
        Inputs:
            s - the current state
            a - the action
            s_ - the next state
            k - the current episode
            h - the timestep within episode when s was visited (starting at zero)
        '''
        #Step 10
#         self.X[h,:] = self.feature_vector(s,a,h) # do not need to store this
        X = self.feature_vector(s,a,h)
        #Step 11
        y = self.V[h+1][self.state_idx[s_]]
#         if s_ != None:
#             y = self.V[h+1][s_]
#         else:
#             y = 0.0
        #Step 12
        self.M = self.M + np.outer(X,X)
        #Step 13
        self.w = self.w + y*X

    def update_param(self):
        '''
        Updates our approximation of theta_star at the end of each episode, see
        Step 15 of algorithm1
        '''
        #Step 15
        #print(self.M)
        self.theta = np.matmul(np.linalg.inv(self.M),self.w)

    def act(self,s,h,k):
        '''
        Returns the greedy action with respect to Q_{h,k}(s,a) for a \in A
        see step 8 of algorithm 1
        Inputs:
            s - the current state
            h - the current timestep within the episode
        '''
        #step 8
        if k > self.K/self.random_explore:
            return self.env.argmax(self.Q[h][self.state_idx[s],:])
        else:
            return bernoulli.rvs(0.5) #A random policy for testing

    def createIdx(self):
        '''
        A simple function that creates sigma according to Appendix B.
        Here sigma is a dictionary who inputs is a tuple (s,a,s') and stores
        the interger index to be used in our basis model P.
        '''
        i = 0
        j = 0
        k = 0
        for s in self.env.states.keys():
            self.state_idx[s] = int(j)
            j += 1
            for a in range(self.env.nAction):
                for s_ in self.env.states.keys():
                    self.sigma[(s,a,s_)] = int(i)
                    i += 1

    def Beta(self,k):
        '''
        A function that return Beta_k according to Algorithm 1, step 3
        '''
        #Step 3
        #Bonus as according to step 3
        #return 16*pow(self.m_2,2)*pow(env.epLen,2)*self.d*np.log(1+env.epLen*k) \
        #    *np.log(pow(k+1,2)*env.epLen/self.delta)*np.log(pow(k+1,2)*env.epLen/self.delta)

        #Confidence bound from Chapter 20 of the Bandit Algorithms book, see Theorem 20.5.
        first = np.sqrt(self.lam)*self.m_2
        #second = np.sqrt(2*np.log(1/self.delta) + self.d*np.log((self.d*self.lam + k*self.L*self.L)/(self.d*self.lam)))
        second = np.sqrt(2*np.log(1/self.delta) + np.log(k*(np.linalg.det(self.M)) / (pow(self.lam,self.d))))
        return first + second

    def run(self):
        R = []
        reward = 0.0
        for k in tqdm(range(1,self.K+1)):
            self.env.reset()
            done = 0
            while done != 1:
                s = self.env.state
                h = self.env.timestep
                a = self.act(s,h,k)
                r,s_,done = self.env.advance(a)
                reward += r
                #count[s,s_] += 1
                self.update_stat(s,a,s_,h)
            self.update_param()
            self.update_Qend(k)
            R.append(reward)
        return R

    def name(self):
        return 'UCRL_VTR'
