#coding=utf-8

from keras import regularizers
from keras.layers import Conv2D,MaxPooling2D,UpSampling2D,BatchNormalization,Reshape,Lambda,Activation,Deconv2D,Concatenate,Permute,Softmax,SpatialDropout2D,Add,Multiply
from keras import backend as K
from .keras_layer_L2Normalization import L2Normalization
import tensorflow as tf

if K.image_dim_ordering() == 'tf':
    bn_axis = 3
else:
    bn_axis = 1

def conv_block(input_tensor, filters, kernel_size, strides, name, padding='same', dila=1):
    x = Conv2D(filters, kernel_size, strides=strides, name= name, padding=padding, kernel_initializer='he_uniform',kernel_regularizer=regularizers.l1_l2(l1=1e-4, l2=1e-5),dilation_rate=dila)(input_tensor)
    x = BatchNormalization(axis=bn_axis, name='bn_'+ name)(x)
    x = Activation('relu')(x)
    return x

def backend_expand_dims_1(x):
    return K.expand_dims(x, axis=1)

def backend_expand_dims_last(x):
    return K.expand_dims(x, axis=-1)

def backend_dot(x):
    return K.batch_dot(x[0], x[1])

def global_context_block(x, channels):
    bs, h, w, c = x.shape.as_list()
    input_x = x
    input_x = Reshape((h * w, c))(input_x)  # [N, H*W, C]
    input_x = Permute((2,1))(input_x)       # [N, C, H*W]
    input_x = Lambda(backend_expand_dims_1,name='a')(input_x)  # [N, 1, C, H*W]

    context_mask = Conv2D(1,(1,1), name='gc-conv0')(x)
    context_mask = Reshape((h * w, 1))(context_mask) # [N, H*W, 1]
    context_mask = Softmax(axis=1)(context_mask)  # [N, H*W, 1]
    context_mask = Permute((2,1))(context_mask)   # [N, 1, H*W]
    context_mask = Lambda(backend_expand_dims_last,name='b')(context_mask) # [N, 1, H*W, 1]

    context = Lambda(backend_dot,name='c')([input_x, context_mask])
    context = Reshape((1,1,c))(context) # [N, 1, 1, C]

    context_transform = conv_block(context, channels, 1, strides=1, name='gc-conv1')
    context_transform = Conv2D(c,(1,1), name='gc-conv2')(context_transform)
    context_transform = Activation('sigmoid')(context_transform)
    x = Multiply()([x , context_transform])

    context_transform = conv_block(context, channels, 1, strides=1, name='gc-conv3')
    context_transform = Conv2D(c,(1,1), name='gc-conv4')(context_transform)
    x = Add()([x,context_transform])

    return x
# -----

def Net(n_label,img_input, drop_rate=0.2):

    # ---------left branch -----
    x = conv_block(img_input, 32, (3, 3), strides=1, name='L_conv1-1')
    x = SpatialDropout2D(drop_rate)(x)
    L1 = conv_block(x, 32, (3, 3), strides=1, name='L_conv1-2')
    x = conv_block(L1, 32, (3, 3), strides=2, name='L_conv1-3')
    #   400 -> 200

    x = conv_block(x, 64, (3, 3), strides=1, name='L_conv2-1')
    x = SpatialDropout2D(drop_rate)(x)
    L2 = conv_block(x, 64, (3, 3), strides=1, name='L_conv2-2')
    x = conv_block(L2, 32, (3, 3), strides=2, name='L_conv2-3')
    #   200 -> 100

    x = conv_block(x, 128, (3, 3), strides=1, name='L_conv3-1')
    x = SpatialDropout2D(drop_rate)(x)
    L3 = conv_block(x, 128, (3, 3), strides=1, name='L_conv3-2')
    x = conv_block(L3, 32, (3, 3), strides=2, name='L_conv3-3')
    #   100 -> 50

    x = conv_block(x, 256, (3, 3), strides=1, name='L_conv4-1')
    x = SpatialDropout2D(drop_rate)(x)
    L4 = conv_block(x, 256, (3, 3), strides=1, name='L_conv4-2')
    x = conv_block(L4, 32, (3, 3), strides=2, name='L_conv4-3')
    #   50 -> 25

    x = conv_block(x, 512, (3, 3), strides=1, name='L_conv5-1')
    x = conv_block(x, 512, (3, 3), strides=1, dila=2, name='L_conv5-2')
    x = SpatialDropout2D(drop_rate)(x)
    x = conv_block(x, 512, (3, 3), strides=1, dila=2, name='L_conv5-3')
    L5 = conv_block(x, 512, (3, 3), strides=1, name='L_conv5-4')

    #    25


    # ---------Right branch -----

    #   25 -> 50
    x = Deconv2D(256, kernel_size=2, strides=2, padding='same',name='R_conv1-1')(L5)
    x = BatchNormalization(axis=bn_axis, name='R_conv1-1_' + 'bn')(x)
    x = conv_block(Concatenate(axis=-1)([x, L4]), 256, (3, 3), strides=1, name='R_conv1-2')
    x = SpatialDropout2D(0.1)(x)
    x = conv_block(x, 256, (3, 3), strides=1, name='R_conv1-3')
    R_out1 = Conv2D(n_label,(1,1),name='R_out1')(x)

    #   50 -> 100
    x = Deconv2D(128, kernel_size=2, strides=2, padding='same', name='R_conv2-1')(x)
    x = BatchNormalization(axis=bn_axis, name='R_conv2-1_' + 'bn')(x)
    x = conv_block(Concatenate(axis=-1)([x, L3]), 128, (3, 3), strides=1, name='R_conv2-2')
    x = SpatialDropout2D(0.1)(x)
    x = conv_block(x, 128, (3, 3), strides=1, name='R_conv2-3')
    R_out2 = Conv2D(n_label, (1, 1), name='R_out2')(x)

    #   100 -> 200
    x = Deconv2D(64, kernel_size=2, strides=2, padding='same', name='R_conv3-1')(x)
    x = BatchNormalization(axis=bn_axis, name='R_conv3-1_' + 'bn')(x)
    x = conv_block(Concatenate(axis=-1)([x, L2]), 64, (3, 3), strides=1, name='R_conv3-2')
    x = SpatialDropout2D(0.1)(x)
    x = conv_block(x, 64, (3, 3), strides=1, name='R_conv3-3')
    R_out3 = Conv2D(n_label, (1, 1), name='R_out3')(x)

    #   200 -> 400
    x = Deconv2D(32, kernel_size=2, strides=2, padding='same', name='R_conv4-1')(x)
    x = BatchNormalization(axis=bn_axis, name='R_conv4-1_' + 'bn')(x)
    x = conv_block(Concatenate(axis=-1)([x, L1]), 32, (3, 3), strides=1, name='R_conv4-2')
    x = SpatialDropout2D(0.1)(x)
    x = conv_block(x, 32, (3, 3), strides=1, name='R_conv4-3')
    R_out4 = Conv2D(n_label, (1, 1), name='R_out4')(x)

    # ---------Recoding branch -----

    x = conv_block(R_out4, 32, (1, 1), strides=1, name='E_conv1-1')
    x = conv_block(x, 32, (3, 3), strides=1, name='E_conv1-2')
    x = SpatialDropout2D(drop_rate)(x)
    x = conv_block(x, 32, (3, 3), strides=2, name='E_conv1-3')
    #   400 -> 200

    x = conv_block(Concatenate(axis=-1)([x, conv_block(R_out3,64, (1, 1), strides=1,name='c1')]), 64, (3, 3), strides=1, name='E_conv2-1')
    x = conv_block(x, 64, (3, 3), strides=1, name='E_conv2-2')
    x = SpatialDropout2D(drop_rate)(x)
    x = conv_block(x, 64, (3, 3), strides=2, name='E_conv2-3')
    #   200 -> 100

    x = conv_block(Concatenate(axis=-1)([x, conv_block(R_out2,128, (1, 1), strides=1,name='c2')]), 128, (3, 3), strides=1, name='E_conv3-1')
    x = conv_block(x, 128, (3, 3), strides=1, name='E_conv3-2')
    x = SpatialDropout2D(drop_rate)(x)
    x = conv_block(x, 128, (3, 3), strides=2, name='E_conv3-3')
    #   100 -> 50

    x = conv_block(Concatenate(axis=-1)([x, conv_block(R_out1,256, (1, 1), strides=1,name='c3')]), 256, (3, 3), strides=1, name='E_conv4-1')
    x = conv_block(x, 256, (3, 3), strides=1, name='E_conv4-2')
    x = SpatialDropout2D(drop_rate)(x)
    x = conv_block(x, 256, (3, 3), strides=1, dila=2, name='E_conv4-3')
    x = conv_block(x, 256, (3, 3), strides=1, dila=2, name='E_conv4-4')
    x = conv_block(x, 256, (3, 3), strides=1, name='E_conv4-5')
    #   50

    x = global_context_block(x, channels=64)
# -----------------------------------------
    final_out = Conv2D(n_label,(1,1), name='final_out')(x)
    final_out = UpSampling2D(size=(8,8))(final_out)

    final_out = Activation('softmax',name='l0')(Reshape((400 * 400, n_label))(final_out))
    out1 = Activation('softmax',name='l1')(Reshape((400 * 400, n_label))(R_out4))
    out2 = Activation('softmax',name='l2')(Reshape((200 * 200, n_label))(R_out3))
    out3 = Activation('softmax',name='l3')(Reshape((100 * 100, n_label))(R_out2))
    out4 = Activation('softmax',name='l4')(Reshape((50 * 50, n_label))(R_out1))

    return [final_out, out1, out2, out3, out4]


