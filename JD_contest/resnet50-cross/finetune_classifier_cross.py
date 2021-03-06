import argparse
import os
import shutil
import time

import torch
import torch.nn as nn
import torch.nn.parallel
import torch.backends.cudnn as cudnn
import torch.distributed as dist
import torch.optim
import torch.utils.data
import torch.utils.data.distributed
import torchvision.transforms as transforms
import torchvision.datasets as datasets
import torchvision.models as models

model_names = sorted(name for name in models.__dict__
    if name.islower() and not name.startswith("__")
    and callable(models.__dict__[name]))

parser = argparse.ArgumentParser(description='pig train')
parser.add_argument('data', metavar='DIR',default='/usr/JD/raw/train/train_set/',
                    help='path to dataset')
parser.add_argument('--arch', '-a', metavar='ARCH', default='resnet18',
                    choices=model_names,
                    help='model architecture: ' +
                        ' | '.join(model_names) +
                        ' (default: resnet18)')
parser.add_argument('-j', '--workers', default=4, type=int, metavar='N',
                    help='number of data loading workers (default: 4)')
parser.add_argument('--epochs', default=10, type=int, metavar='N',
                    help='number of total epochs to run')
parser.add_argument('--start-epoch', default=0, type=int, metavar='N',
                    help='manual epoch number (useful on restarts)')
parser.add_argument('-b', '--batch-size', default=64, type=int,
                    metavar='N', help='mini-batch size (default: 256)')
parser.add_argument('--lr', '--learning-rate', default=0.001, type=float,
                    metavar='LR', help='initial learning rate')
parser.add_argument('--momentum', default=0.9, type=float, metavar='M',
                    help='momentum')
parser.add_argument('--weight-decay', '--wd', default=1e-4, type=float,
                    metavar='W', help='weight decay (default: 1e-4)')
parser.add_argument('--print-freq', '-p', default=10, type=int,
                    metavar='N', help='print frequency (default: 10)')
parser.add_argument('--resume', default='', type=str, metavar='PATH',
                    help='path to latest checkpoint (default: none)')
parser.add_argument('-e', '--evaluate', dest='evaluate', action='store_true',
                    help='evaluate model on validation set')
parser.add_argument('--pretrained', dest='pretrained', action='store_true',
                    help='use pre-trained model')
parser.add_argument('--world-size', default=1, type=int,
                    help='number of distributed processes')
parser.add_argument('--dist-url', default='tcp://224.66.41.62:23456', type=str,
                    help='url used to set up distributed training')
parser.add_argument('--dist-backend', default='gloo', type=str,
                    help='distributed backend')

parser.add_argument('-s', '--sequence', default=1, type=int,
                    metavar='N', help='the sequence of cross validation (1-5)')

best_prec1 = 0
best_loss1 = 1000


def main():
    global args, best_prec1,best_loss1
    args = parser.parse_args()

    args.distributed = args.world_size > 1

    if args.distributed:
        dist.init_process_group(backend=args.dist_backend, init_method=args.dist_url,
                                world_size=args.world_size)

    # create model
    if args.pretrained:
        print("=> using pre-trained model '{}'".format(args.arch))
        model = models.__dict__[args.arch](pretrained=True)
    else:
        print("=> creating model '{}'".format(args.arch))
        model = models.__dict__[args.arch]()
    print(model)
######################

    for parma in model.parameters():
       parma.requires_grad = False

    if args.arch.startswith('vgg'):
        # model.classifier = torch.nn.Sequential(torch.nn.Linear(25088, 4096),
        #                                torch.nn.ReLU(),
        #                                torch.nn.Dropout(p=0.5),
        #                                torch.nn.Linear(4096, 4096),
        #                                torch.nn.ReLU(),
        #                                torch.nn.Dropout(p=0.5),
        #                                torch.nn.Linear(4096, 30))

        mod = list(model.classifier.children())
        mod.pop()
        mod.append(torch.nn.Linear(4096, 30))
        new_classifier = torch.nn.Sequential(*mod)
        model.classifier = new_classifier
        
        
    elif args.arch.startswith('alexnet'):
        mod = list(model.classifier.children())
        mod.pop()
        mod.append(torch.nn.Linear(4096, 30))
        new_classifier = torch.nn.Sequential(*mod)
        model.classifier = new_classifier
    else:
        model.fc=torch.nn.Linear(2048, 30)
    
    print(model)
    ########################


    model.cuda()


    # define loss function (criterion) and optimizer
    criterion = nn.CrossEntropyLoss().cuda()

    # for index, parma in enumerate(model.classifier.parameters()):
    #     if index == 6:
    #         parma.requires_grad = True
#####################
    # optimizer = torch.optim.SGD(model.fc.parameters(), args.lr,
    #                             momentum=args.momentum,
    #                             weight_decay=args.weight_decay)
    optimizer = torch.optim.Adam(model.fc.parameters(), args.lr,
                                weight_decay=args.weight_decay)
#######################
    # optionally resume from a checkpoint
    if args.resume:
        if os.path.isfile(args.resume):
            print("=> loading checkpoint '{}'".format(args.resume))
            checkpoint = torch.load(args.resume)
            args.start_epoch = checkpoint['epoch']
            best_prec1 = checkpoint['best_prec1']
            model.load_state_dict(checkpoint['state_dict'])
            optimizer.load_state_dict(checkpoint['optimizer'])
            print("=> loaded checkpoint '{}' (epoch {})"
                  .format(args.resume, checkpoint['epoch']))
        else:
            print("=> no checkpoint found at '{}'".format(args.resume))
######################
    train_name = args.arch + '_' + args.batch_size + '_' + args.epoch

    logpath_train='./log_resnet50/train/' + train_name + '/'
    txtname=str(args.sequence) + 'train.csv'
    if not os.path.exists(logpath_train):
        os.makedirs(logpath_train)
    if os.path.exists(logpath_train+txtname):
        os.remove(logpath_train+txtname)
    global f_train
    f_train=file(logpath_train+txtname,'a+')
    #title='Epoch '+'Loss '+'Prec@1 '+'Prec@5'+'/n'
    #f.write(title)

    global logpath_val
    logpath_val='./log_resnet50/val/' + train_name + '/'
    txtname=str(args.sequence) + 'val.csv'
    if not os.path.exists(logpath_val):
        os.makedirs(logpath_val)
    if os.path.exists(logpath_val+txtname):
        os.remove(logpath_val+txtname)
    global f_val
    f_val=file(logpath_val+txtname,'a+')
    #title='Prec@1 '+'Prec@5'+'/n'
    #f.write(title)
#################
    cudnn.benchmark = True

    # Data loading code
    traindir = os.path.join(args.data, 'train_set_'+str(args.sequence), 'train')
    valdir = os.path.join(args.data, 'train_set_'+str(args.sequence), 'val')
    normalize = transforms.Normalize(mean=[0.485, 0.456, 0.406],
                                     std=[0.229, 0.224, 0.225])

    train_dataset = datasets.ImageFolder(
        traindir,
        transforms.Compose([
            #transforms.CenterCrop([224.224]),
            transforms.Scale([224,224]),
            transforms.RandomHorizontalFlip(),
            #transforms.RandomVerticalFlip(),
            transforms.ToTensor(),
            normalize,
        ]))

    if args.distributed:
        train_sampler = torch.utils.data.distributed.DistributedSampler(train_dataset)
    else:
        train_sampler = None

    train_loader = torch.utils.data.DataLoader(
        train_dataset, batch_size=args.batch_size, shuffle=(train_sampler is None),
        num_workers=args.workers, pin_memory=True, sampler=train_sampler)

    val_loader = torch.utils.data.DataLoader(
        datasets.ImageFolder(valdir, transforms.Compose([
            transforms.Scale([224,224]),
            transforms.ToTensor(),
            normalize,
        ])),
        batch_size=args.batch_size, shuffle=False,
        num_workers=args.workers, pin_memory=True)

    if args.evaluate:
        validate(val_loader, model, criterion)
        return

    print(str(args.sequence) + ' strat to train\nthe dir of train and val is as follow')
    print(traindir)
    print(valdir)

    for epoch in range(args.start_epoch, args.epochs):
        if args.distributed:
            train_sampler.set_epoch(epoch)
        # adjust_learning_rate(optimizer, epoch)  # adjust ls every 8 epochs
        print(optimizer.param_groups[0]['lr'])
        # train for one epoch
        train(train_loader, model, criterion, optimizer, epoch)

        # evaluate on validation set
        prec1,val_loss = validate(val_loader, model, criterion)

        # remember best prec@1 and save checkpoint
        is_best = val_loss < best_loss1
        best_loss1 = min(val_loss, best_loss1)
        save_checkpoint({   # this is a function
            'epoch': epoch + 1,
            'arch': args.arch,
            'state_dict': model.state_dict(),
            'best_prec1': best_prec1,
            'optimizer' : optimizer.state_dict(),
        }, is_best, val_loss)
       ######
        # save_path=logpath_val+args.data.split('/')[-1]
        # if not os.path.exists(save_path):
        #     os.makedirs(save_path)
        # torch.save(model.state_dict(), '%s/model_epoch_%d.pth' % (save_path, epoch))


def train(train_loader, model, criterion, optimizer, epoch):
    batch_time = AverageMeter()
    data_time = AverageMeter()
    losses = AverageMeter()
    top1 = AverageMeter()
    top5 = AverageMeter()

    # switch to train mode
    model.train()

    end = time.time()
    for i, (input, target) in enumerate(train_loader):
        
        # measure data loading time
        data_time.update(time.time() - end)

        target = target.cuda(async=True)
        input_var = torch.autograd.Variable(input).cuda()
        target_var = torch.autograd.Variable(target)

        # compute output
        output = model(input_var)
        loss = criterion(output, target_var)

        # measure accuracy and record loss
        prec1, prec5 = accuracy(output.data, target, topk=(1, 5))
        losses.update(loss.data[0], input.size(0))
        top1.update(prec1[0], input.size(0))
        top5.update(prec5[0], input.size(0))

        # compute gradient and do SGD step
        optimizer.zero_grad()
        loss.backward()
        optimizer.step()

        # measure elapsed time
        batch_time.update(time.time() - end)
        end = time.time()

        if i % args.print_freq == 0:
            print('Epoch: [{0}][{1}/{2}]\t'
                  'Time {batch_time.val:.3f} ({batch_time.avg:.3f})\t'
                  'Data {data_time.val:.3f} ({data_time.avg:.3f})\t'
                  'Loss {loss.val:.4f} ({loss.avg:.4f})\t'
                  'Prec@1 {top1.val:.3f} ({top1.avg:.3f})\t'
                  'Prec@5 {top5.val:.3f} ({top5.avg:.3f})'.format(
                   epoch, i, len(train_loader), batch_time=batch_time,
                   data_time=data_time, loss=losses, top1=top1, top5=top5))
            f_train.writelines('Epoch: [{0}][{1}/{2}]\t'
                  'Time {batch_time.val:.3f} ({batch_time.avg:.3f})\t'
                  'Data {data_time.val:.3f} ({data_time.avg:.3f})\t'
                  'Loss {loss.val:.4f} {loss.avg:.4f}\t'
                  'Prec@1 {top1.val:.3f} ({top1.avg:.3f})\t'
                  'Prec@5 {top5.val:.3f} ({top5.avg:.3f}) \n'.format(
                   epoch, i, len(train_loader), batch_time=batch_time,
                   data_time=data_time, loss=losses, top1=top1, top5=top5))



def validate(val_loader, model, criterion):
    batch_time = AverageMeter()
    losses = AverageMeter()
    top1 = AverageMeter()
    top5 = AverageMeter()

    # switch to evaluate mode
    model.eval()

    end = time.time()
    for i, (input, target) in enumerate(val_loader):
        target = target.cuda(async=True)
        input_var = torch.autograd.Variable(input, volatile=True).cuda()
        target_var = torch.autograd.Variable(target, volatile=True)

        # compute output
        output = model(input_var)
        loss = criterion(output, target_var)

        # measure accuracy and record loss
        prec1, prec5 = accuracy(output.data, target, topk=(1, 5))
        losses.update(loss.data[0], input.size(0))
        top1.update(prec1[0], input.size(0))
        top5.update(prec5[0], input.size(0))

        # measure elapsed time
        batch_time.update(time.time() - end)
        end = time.time()

        if i % args.print_freq == 0:
            print('Test: [{0}/{1}]\t'
                  'Time {batch_time.val:.3f} ({batch_time.avg:.3f})\t'
                  'Loss {loss.val:.4f} ({loss.avg:.4f})\t'
                  'Prec@1 {top1.val:.3f} ({top1.avg:.3f})\t'
                  'Prec@5 {top5.val:.3f} ({top5.avg:.3f})'.format(
                   i, len(val_loader), batch_time=batch_time, loss=losses,
                   top1=top1, top5=top5))

    print(' * Prec@1 {top1.avg:.3f} Prec@5 {top5.avg:.3f}\t'
              'Loss {loss.val:.4f} ({loss.avg:.4f})'
          .format(loss=losses,top1=top1, top5=top5))
    f_val.writelines(' * Prec@1 {top1.avg:.3f} Prec@5 {top5.avg:.3f}\t'
              'Loss {loss.val:.4f} {loss.avg:.4f}\n'
          .format(loss=losses,top1=top1, top5=top5))

    return top1.avg, losses.avg


def save_checkpoint(state, is_best, val_loss, filename='_checkpoint.pth.tar'):
    global args
    tmp_name = str(args.sequence) + '_' + str(val_loss)+filename
    torch.save(state, tmp_name)
    if is_best:
        shutil.copyfile(tmp_name, str(args.sequence)+'_model_best.pth.tar') # tmp_name includes sequence


class AverageMeter(object):
    """Computes and stores the average and current value"""
    def __init__(self):
        self.reset()

    def reset(self):
        self.val = 0
        self.avg = 0
        self.sum = 0
        self.count = 0

    def update(self, val, n=1):
        self.val = val
        self.sum += val * n
        self.count += n
        self.avg = self.sum / self.count


def adjust_learning_rate(optimizer, epoch):
    """Sets the learning rate to the initial LR decayed by 10 every 30 epochs"""
    lr = args.lr * (0.05 ** (epoch // 8))   # adjust ls every 8 epochs
    for param_group in optimizer.param_groups:
        param_group['lr'] = lr


def accuracy(output, target, topk=(1,)):
    """Computes the precision@k for the specified values of k"""
    maxk = max(topk)
    batch_size = target.size(0)

    _, pred = output.topk(maxk, 1, True, True)
    pred = pred.t()
    correct = pred.eq(target.view(1, -1).expand_as(pred))

    res = []
    for k in topk:
        correct_k = correct[:k].view(-1).float().sum(0, keepdim=True)
        res.append(correct_k.mul_(100.0 / batch_size))
    return res


if __name__ == '__main__':
    main()
