#!python
from __future__ import with_statement
from __future__ import division
from __future__ import absolute_import
from __future__ import print_function
from collections import Counter
import operator

WB_DOC_CNT= u'###DOC_CNT###' #Used for Spark document counting across RDFs

def batch_get_dfs(args):
	dft= Counter()
	for text in args[0]:
		for word in set(text.split(" ")):  dft[word]+= 1
	dft[WB_DOC_CNT]+= len(args[0]) #Avoid Spark collect() by counting here
	return dft

class Dictionary(object):
	def __init__(self, batcher, min_df=0, max_df=1.0, max_words= 10000000000000, freeze= False, verbose=1):
		self.verbose = verbose
		self.freeze = freeze
		self.max_words = max_words
		self.min_df = min_df
		self.max_df = max_df
		self.batcher= batcher
		self.reset()

	def reset(self):
		self.word2id = {}
		self.dft = Counter()
		self.doc_count = 0
		return self

	def get_pruning_dft(self, dft):
		sorted_dft = sorted(list(dft.items()), key=operator.itemgetter(1), reverse=True)
		if type(self.min_df) == type(1):  min_df2 = self.min_df
		else:  min_df2 = self.doc_count * self.min_df
		if type(self.max_df) == type(1):   max_df2 = self.max_df
		else:  max_df2 = self.doc_count * self.max_df
		return sorted_dft, min_df2, max_df2

	def prune_dictionary(self, max_words=None, min_df=None, max_df=None, re_encode= False, prune_dfs= True,
						 set_max_words= True):
		#Prune dictionary. Optionally prune document frequency table as well
		if max_words!=None: self.max_words= max_words
		if min_df!=None: self.min_df= min_df
		if max_df!= None: self.max_df= max_df
		max_words= self.max_words
		word2id = self.word2id
		dft = self.dft
		sorted_dft, min_df2, max_df2 = self.get_pruning_dft(dft)
		c= 0
		print(len(sorted_dft), len(self.word2id), len(self.raw_dft))
		for word, df in sorted_dft:
			if word not in word2id:
				if re_encode:  word2id[word]= -1
				else:  continue
			c+= 1
			if c > max_words or df < min_df2 or df > max_df2:
				if prune_dfs: dft.pop(word)
				word2id.pop(word)
			elif re_encode:
				word2id[word]= c
		if set_max_words:  self.max_words= len(word2id)

	def fit(self, data, input_split= False, reset= False):
		if reset:  self.reset()
		dft= self.dft
		word2id= self.word2id
		dfts= self.batcher.parallelize_batches(batch_get_dfs, data, [], input_split= input_split, merge_output=False)
		if self.batcher.spark_context is not None:  dfts= [batch[1] for batch in dfts.collect()]
		self.doc_count+= sum([dft2.pop(WB_DOC_CNT) for dft2 in dfts])
		for dft2 in dfts:  dft.update(dft2)

		#print(dft)
		if word2id!=None:
			#Add entries. Online pruning only used to prevent inclusion into dictionary
			sorted_dft, min_df2, max_df2 = self.get_pruning_dft(dft)
			for word, df in sorted_dft:
				if len(word2id)>= self.max_words: break
				if df<min_df2 or df>max_df2: continue
				if word in word2id:  continue
				word2id[word] = len(word2id)+1
				if self.verbose>2: print("Add word to dictionary:", word, dft[word], word2id[word])
		return self

	def fit_transform(self, data, input_split= False, merge_output= True, reset= False):
		self.fit(data, input_split, reset)
		return self.transform(data, input_split= input_split, merge_output= merge_output)

	def transform(self, data, input_split= False, merge_output= True):
		if input_split and merge_output: data= self.batcher.merge_batches(data)
		return data