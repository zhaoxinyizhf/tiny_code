# -*-coding:utf-8-*-
"""
This part of code is the DQN brain, which is a brain of the agent.
All decisions are made in here.
Using Tensorflow to build the neural network.

View more on my tutorial page: https://morvanzhou.github.io/tutorials/

Using:
Tensorflow: 1.0
gym: 0.7.3
"""

import numpy as np
import pandas as pd
import tensorflow as tf

np.random.seed(1)
tf.set_random_seed(1)


# Deep Q Network off-policy
class DeepQNetwork:
    def __init__(
            self,
            n_actions,
            n_features,
            learning_rate=0.01,
            reward_decay=0.9,
            e_greedy=0.9,   # epsilon最大值
            replace_target_iter=300,
            memory_size=500,
            batch_size=32,
            e_greedy_origin=0.6,    # epsilon初始值
            e_greedy_increment=None,    # 是一个增量，而不是乘法
            output_graph=False,
            model_load=False,
            model_load_dir=None,
            model_save_dir=None,
    ):
        self.n_actions = n_actions
        self.n_features = n_features
        self.lr = learning_rate
        self.gamma = reward_decay
        self.epsilon_max = e_greedy
        self.replace_target_iter = replace_target_iter
        self.memory_size = memory_size
        self.batch_size = batch_size
        self.epsilon_increment = e_greedy_increment
        self.epsilon = e_greedy_origin if e_greedy_increment is not None else self.epsilon_max
        self.model_load = model_load
        self.model_load_dir = model_load_dir
        self.model_save_dir = model_save_dir
        # total learning step
        self.learn_step_counter = 0 # 用于记录

        # initialize zero memory [s, s_] + reward + action
        self.memory = np.zeros((self.memory_size, n_features * 2 + 2))  # 初始化

        # consist of [target_net, evaluate_net]
        self._build_net()
        # tf.get_collection是tensorflow读取参数方式
        t_params = tf.get_collection('target_net_params')   # t_params目标函数，每隔一定次数迭代才会更新
        e_params = tf.get_collection('eval_net_params') # e_params即时更新的参数
        # 这是定义了一个函数吗，直接用e_params覆盖t_params??????????????????????????????
        self.replace_target_op = [tf.assign(t, e) for t, e in zip(t_params, e_params)]  # tf.assign(ref, value) # 更新target_params

        self.sess = tf.Session()

        if output_graph:    # save
            # $ tensorboard --logdir=logs
            # tf.train.SummaryWriter soon be deprecated, use following
            tf.summary.FileWriter("logs/", self.sess.graph)

        self.sess.run(tf.global_variables_initializer())    # 运行必须的命令
        if self.model_load:

            saver = tf.train.Saver()
            saver.restore(self.sess, self.model_load_dir)
            print("Model restored")

        self.cost_his = []  # 记录每一步的误差

    def _build_net(self):
        # ------------------ build evaluate_net ------------------
        # s是当前步的状态，什么意思？？？？？？？？？？？？？
        self.s = tf.placeholder(tf.float32, [None, self.n_features], name='s')  # input # tf.placeholder save data
        self.q_target = tf.placeholder(tf.float32, [None, self.n_actions], name='Q_target')  # for calculating loss
        with tf.variable_scope('eval_net'):
            # c_names(collections_names) are the collections to store variables # collections_names是一个用于储存参数的集合的名称
            # n_l1是神经元的数量，这里改为100个
            c_names, n_l1, w_initializer, b_initializer = \
                ['eval_net_params', tf.GraphKeys.GLOBAL_VARIABLES], 100, \
                tf.random_normal_initializer(0., 0.3), tf.constant_initializer(0.1)  # config of layers

            # first layer. collections is used later when assign to target net
            with tf.variable_scope('l1'):
                w1 = tf.get_variable('w1', [self.n_features, n_l1], initializer=w_initializer, collections=c_names)
                b1 = tf.get_variable('b1', [1, n_l1], initializer=b_initializer, collections=c_names)
                l1 = tf.nn.relu(tf.matmul(self.s, w1) + b1)

            # second layer. collections is used later when assign to target net
            with tf.variable_scope('l2'):
                w2 = tf.get_variable('w2', [n_l1, self.n_actions], initializer=w_initializer, collections=c_names)
                b2 = tf.get_variable('b2', [1, self.n_actions], initializer=b_initializer, collections=c_names)
                self.q_eval = tf.matmul(l1, w2) + b2

            with tf.variable_scope('l3'):
                w3 = tf.get_variable('w3', [self.n_features, n_l1], initializer=w_initializer, collections=c_names)
                b3 = tf.get_variable('b3', [1, n_l1], initializer=b_initializer, collections=c_names)
                l3 = tf.nn.relu(tf.matmul(self.s, w3) + b3)

        with tf.variable_scope('loss'):
            self.loss = tf.reduce_mean(tf.squared_difference(self.q_target, self.q_eval))   # loss
        with tf.variable_scope('train'):
            self._train_op = tf.train.RMSPropOptimizer(self.lr).minimize(self.loss) # Optimizer

        # ------------------ build target_net ------------------
        # s_是下一步的状态什么意思
        self.s_ = tf.placeholder(tf.float32, [None, self.n_features], name='s_')    # input
        with tf.variable_scope('target_net'):
            # c_names(collections_names) are the collections to store variables
            c_names = ['target_net_params', tf.GraphKeys.GLOBAL_VARIABLES]

            # 两个网络要保持一致，所以这个网络参数直接用之前定义的
            # first layer. collections is used later when assign to target net
            with tf.variable_scope('l1'):
                w1 = tf.get_variable('w1', [self.n_features, n_l1], initializer=w_initializer, collections=c_names)
                b1 = tf.get_variable('b1', [1, n_l1], initializer=b_initializer, collections=c_names)
                l1 = tf.nn.relu(tf.matmul(self.s_, w1) + b1)

            # second layer. collections is used later when assign to target net
            with tf.variable_scope('l2'):
                w2 = tf.get_variable('w2', [n_l1, self.n_actions], initializer=w_initializer, collections=c_names)
                b2 = tf.get_variable('b2', [1, self.n_actions], initializer=b_initializer, collections=c_names)
                self.q_next = tf.matmul(l1, w2) + b2

            with tf.variable_scope('l3'):
                w3 = tf.get_variable('w3', [self.n_features, n_l1], initializer=w_initializer, collections=c_names)
                b3 = tf.get_variable('b3', [1, n_l1], initializer=b_initializer, collections=c_names)
                l3 = tf.nn.relu(tf.matmul(self.s, w3) + b3)

    def store_transition(self, s, a, r, s_):
        if not hasattr(self, 'memory_counter'): # 循环覆盖
            self.memory_counter = 0

        transition = np.hstack((s, [a, r], s_)) # 组合成向量

        # replace the old memory with new memory
        index = self.memory_counter % self.memory_size
        self.memory[index, :] = transition

        self.memory_counter += 1

    def choose_action(self, observation):
        # to have batch dimension when feed into tf placeholder
        observation = observation[np.newaxis, :]    # np.newaxis create new dimension   # observation输入的时候是一维的数据

        if np.random.uniform() < self.epsilon:  # random decide whether explore randomly
            # forward feed the observation and get q value for every actions
            actions_value = self.sess.run(self.q_eval, feed_dict={self.s: observation})
            action = np.argmax(actions_value)
        else:
            action = np.random.randint(0, self.n_actions)
        return action

    def learn(self):
        # check to replace target parameters
        if self.learn_step_counter % self.replace_target_iter == 0:
            self.sess.run(self.replace_target_op)
            print('\ntarget_params_replaced\n')

        # sample batch memory from all memory
        if self.memory_counter > self.memory_size:  # 如果总数大于memory_size，就只保留memory_size的大小的数据
            sample_index = np.random.choice(self.memory_size, size=self.batch_size)
        else:
            sample_index = np.random.choice(self.memory_counter, size=self.batch_size)
        batch_memory = self.memory[sample_index, :]

        q_next, q_eval = self.sess.run(
            [self.q_next, self.q_eval],
            feed_dict={
                self.s_: batch_memory[:, -self.n_features:],  # 下一步的状态是最后几组数据
                self.s: batch_memory[:, :self.n_features],  # 当前步的状态是前几组数据
            })

        # change q_target w.r.t q_eval's action
        q_target = q_eval.copy()

        batch_index = np.arange(self.batch_size, dtype=np.int32)
        eval_act_index = batch_memory[:, self.n_features].astype(int)   # 找到对应的列
        reward = batch_memory[:, self.n_features + 1]

        q_target[batch_index, eval_act_index] = reward + self.gamma * np.max(q_next, axis=1)


        ### 自己的理解 ###
        # 反向传播只有选择了的action的值
        # 根据memory选择了哪个action，会得到对应的action的q值，需要和对应的eval值相减，而其他的置0
        """
        For example in this batch I have 2 samples and 3 actions:
        q_eval =
        [[1, 2, 3],
         [4, 5, 6]]

        q_target = q_eval =
        [[1, 2, 3],
         [4, 5, 6]]

        Then change q_target with the real q_target value w.r.t the q_eval's action.
        For example in:
            sample 0, I took action 0, and the max q_target value is -1;
            sample 1, I took action 2, and the max q_target value is -2:
        q_target =
        [[-1, 2, 3],
         [4, 5, -2]]

        So the (q_target - q_eval) becomes:
        [[(-1)-(1), 0, 0],
         [0, 0, (-2)-(6)]]

        We then backpropagate this error w.r.t the corresponding action to network,
        leave other action as error=0 cause we didn't choose it.
        """

        # train eval network
        _, self.cost = self.sess.run([self._train_op, self.loss],
                                     feed_dict={self.s: batch_memory[:, :self.n_features],
                                                self.q_target: q_target})
        self.cost_his.append(self.cost)

        # increasing epsilon
        self.epsilon = self.epsilon + self.epsilon_increment if self.epsilon < self.epsilon_max else self.epsilon_max
        # print("epsilon: ", self.epsilon)  # 输出epsilon
        self.learn_step_counter += 1

    def plot_cost(self):
        import matplotlib.pyplot as plt
        plt.plot(np.arange(len(self.cost_his)), self.cost_his)
        plt.ylabel('Cost')
        plt.xlabel('training steps')
        plt.show()

    def model_saver(self):
        saver = tf.train.Saver(write_version=tf.train.SaverDef.V2)
        saver_path = saver.save(self.sess, self.model_save_dir)
        print("Model saved in: ", saver_path)



